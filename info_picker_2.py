import io
import uuid
import zipfile
import json
import os
import re
from urllib import request

import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pandas as pd
import requests
import yfinance as yf
from typing import Dict, Optional, Tuple, List
from edgar import *
from indicators import compute_ratios

# File path for storing the company list
FILE_PATH = "company_tickers.json"

# Headers for SEC API requests
HEADERS = {
    'User-Agent': 'EdgarAnalytic/0.1 (AlfredNem@gmail.com)'
}

# Aliases to locate variables in XBRL tables
VARIABLE_ALIASES = {
    "total assets": ["total assets", "assets"],
    "total liabilities": ["total liabilities", "liabilities"],
    "cash": ["cash", "cash and cash equivalents at carrying value"],
    "Shares Outstanding": ["Weighted Average Number Of Shares Outstanding Basic"]
}

VARIABLE_SHEETS = {
    "total assets": "balance_sheet",
    "total liabilities": "balance_sheet",
    "cash": "balance_sheet",
    "Shares Outstanding": "income"
}


# ----------------------------- DATA CLASSES ---------------------------------
class CompanyIns:
    def __init__(self, cik_str, ticker, title):
        self.cik = cik_str
        self.ticker = ticker
        self.title = title
        self.years = {}  # dict[int, List[CompanyFinancials]]


class CompanyFinancials:
    def __init__(self, date, filling, location=None):
        self.date = date                    # report date (period end)
        self.financials = filling           # edgar.Financials or a wrapper
        self.location = location            # path to saved JSON snapshot


class CompanyData:
    def __init__(self, data: Dict = None):
        self.companies: Dict[str, CompanyIns] = {}
        if data:
            for key, value in data.items():
                self.companies[key] = CompanyIns(**value)

    def update_companies(self, new_data):
        """Update the company list if there are any changes."""
        new_companies = {
            str(v["cik_str"]): CompanyIns(v["cik_str"], v["ticker"], v["title"])
            for v in new_data.values()
        }

        if self.companies != new_companies:
            print("Updating company list...")
            self.companies = new_companies
            self.save_companies()
        else:
            print("No changes detected in company tickers.")

    def save_companies(self):
        """Save company data to a JSON file."""
        with open(FILE_PATH, "w", encoding="utf-8") as file:
            json.dump({k: v.__dict__ for k, v in self.companies.items()}, file, indent=4)
        print("Company tickers list updated and saved.")

    def load_saved_companies(self):
        """Load previously saved companies from a JSON file."""
        if os.path.exists(FILE_PATH):
            with open(FILE_PATH, "r", encoding="utf-8") as file:
                data = json.load(file)
                self.companies = {
                    k: CompanyIns(
                        cik_str=v.get("cik") or v.get("cik_str"),  # handle both naming variations
                        ticker=v["ticker"],
                        title=v["title"]
                    )
                    for k, v in data.items()
                }
        else:
            print("No saved company list found.")


# ----------------------------- FILE SAVE HELPERS ----------------------------
def save_xbrl_to_disk(xbrl_data, ticker, reporting_date):
    """
    Saves XBRL data to disk and returns the file path.
    """
    directory = "xbrl_data"
    os.makedirs(directory, exist_ok=True)

    safe_date = reporting_date.strftime("%Y-%m-%d")
    filename = f"{ticker}_{safe_date}_{uuid.uuid4().hex[:8]}.xbrl"
    file_path = os.path.join(directory, filename)

    try:
        if isinstance(xbrl_data, bytes):
            with open(file_path, "wb") as f:
                f.write(xbrl_data)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(xbrl_data))
    except Exception as e:
        print(f"Error saving XBRL file: {e}")
        return None

    return file_path


def save_financials_as_json(financials_file, ticker, reporting_date):
    """
    Saves the three statements to JSON (dict-of-dicts) and computes 'computed' section.
    The filename is keyed by the *reporting (period-end) date*.
    """
    directory = f"xbrl_data_json/{ticker}"
    os.makedirs(directory, exist_ok=True)

    safe_date = reporting_date.strftime("%Y-%m-%d")
    filename = f"{ticker}_{safe_date}_{uuid.uuid4().hex[:8]}.json"
    file_path = os.path.join(directory, filename)

    try:
        data = {
            "balance_sheet": financials_file.get_balance_sheet().data.to_dict(),
            "income": financials_file.get_income_statement().data.to_dict(),
            "cashflow": financials_file.get_cash_flow_statement().data.to_dict(),
            "date": safe_date
        }
        computed = compute_ratios(data["balance_sheet"], data["income"], data["cashflow"])
        data["computed"] = computed
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving financials JSON: {e}")
        return None

    return file_path


# ----------------------------- VARIABLE EXTRACT -----------------------------
def get_file_variable(variable, sheet_object, year):
    """
    Finds a variable in a 'Sheet' object (which must expose .data -> DataFrame).
    Prefers exact match; falls back to partial match. Skips abstract concepts.
    """
    try:
        df = sheet_object.data

        if df.empty:
            print(f"[WARNING] DataFrame je prázdný pro rok {year}.")
            return None

        # If 'concept' column exists, filter out Abstract rows
        if "concept" in df.columns:
            df = df[~df["concept"].str.contains("Abstract", case=False, na=False)]

        # Normalize query
        var_norm = variable.strip().lower()

        # Candidate aliases
        candidate_labels = VARIABLE_ALIASES.get(var_norm, [var_norm])

        # 1) Exact match (case-insensitive)
        for name in candidate_labels:
            for row_label in df.index:
                if row_label.strip().lower() == name:
                    value = df.loc[row_label].dropna().iloc[0]
                    print(f"[DEBUG] Načteno: přesná shoda '{row_label}' → {value}")
                    return value

        # 2) Partial match
        for name in candidate_labels:
            for row_label in df.index:
                if name in row_label.strip().lower():
                    value = df.loc[row_label].dropna().iloc[0]
                    print(f"[DEBUG] Načteno: částečná shoda '{row_label}' → {value}")
                    return value

        print(f"[DEBUG] Proměnná '{variable}' nebyla nalezena v žádné podobě.")
        return None

    except Exception as e:
        print(f"[ERROR] Error while extracting variable: {e}")
        return None


# ----------------------------- COMPANY LIST MGMT ----------------------------
def download_company_tickers():
    """Fetch the latest company tickers list from SEC."""
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error downloading company tickers: {response.status_code}")
        return None


def update_company_list():
    """Main function to check for differences and update the company list."""
    new_data = download_company_tickers()
    if not new_data:
        return
    company_data = CompanyData()
    company_data.load_saved_companies()
    company_data.update_companies(new_data)


# ----------------------------- INDEX HELPERS --------------------------------
def download_SP500_tickers():
    req = request.Request('http://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    opener = request.urlopen(req)
    content = opener.read().decode()
    soup = BeautifulSoup(content, features="lxml")
    tables = soup.find_all('table')  # the table we actually need is tables[0]
    external_class = tables[0].findAll('a', {'class': 'external text'})
    tickers = []
    for ext in external_class:
        if 'reports' not in str(ext):
            tickers.append(ext.string)
    return tickers


def download_DJI_tickers():
    req = request.Request('http://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average')
    opener = request.urlopen(req)
    content = opener.read().decode()
    soup = BeautifulSoup(content, features="lxml")
    tables = soup.find_all('table')  # the table we actually need is tables[2]
    external_class = tables[2].findAll('a', {'class': 'external text'})
    tickers = []
    for ext in external_class:
        if 'reports' not in str(ext):
            tickers.append(ext.string)
    return tickers


# ----------------------------- YAHOO HELPERS --------------------------------
def yf_download_series_xy(ticker: str, start_year: int, end_year: int) -> Optional[Tuple[List[pd.Timestamp], List[float]]]:
    """
    Download daily Close from Yahoo Finance and return (x_dates, y_values).
    x_dates are tz-naive pandas Timestamps normalized to 00:00:00 to match filings.
    """
    try:
        start = pd.Timestamp(year=start_year, month=1, day=1)
        end = pd.Timestamp(year=end_year, month=12, day=31) + pd.Timedelta(days=1)

        hist = yf.download(
            tickers=ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True
        )
        if hist is None or hist.empty:
            print(f"[YF][{ticker}] Empty for {start.date()}..{(end - pd.Timedelta(days=1)).date()}")
            return None

        # Robust "Close" extraction for both single- and multi-index columns
        if isinstance(hist.columns, pd.MultiIndex):
            if ('Close', ticker) in hist.columns:
                series = hist[('Close', ticker)]
            elif 'Close' in hist.columns.get_level_values(0):
                series = hist['Close'].iloc[:, 0]
            else:
                series = hist.iloc[:, 0]
        else:
            series = hist.get("Close", hist.iloc[:, 0])

        series = pd.to_numeric(series, errors="coerce").dropna()
        if series.empty:
            print(f"[YF][{ticker}] Series empty after dropna().")
            return None

        idx = pd.to_datetime(series.index)
        try:
            idx = idx.tz_localize(None)
        except Exception:
            pass
        idx = idx.normalize()
        series.index = idx

        print(f"[YF][{ticker}] points={len(series)}, first={series.index[0].date()}, "
              f"last={series.index[-1].date()}, min={float(series.min()):.2f}, max={float(series.max()):.2f}")

        return list(series.index), list(series.values.astype(float))
    except Exception as e:
        print(f"[ERROR] yf_download_series_xy failed for {ticker}: {e}")
        return None


def extract_date_from_filename(filename: str, ticker: str) -> Optional[pd.Timestamp]:
    """
    Expected filename pattern: <TICKER>_YYYY-MM-DD_<anything>.json
    Returns pandas.Timestamp if found, else None.
    """
    m = re.match(rf"^{re.escape(ticker)}_(\d{{4}}-\d{{2}}-\d{{2}})_.*\.json$", filename)
    if not m:
        return None
    try:
        return pd.to_datetime(m.group(1))
    except Exception:
        return None


def yf_get_stock_data(ticker, start_year, end_year):
    """
    Read (and if missing, fetch) Yahoo close price for each JSON filing date we have,
    restricted to the years in [start_year, end_year].
    """
    years = set(range(start_year, end_year + 1))
    stock_data: Dict[str, Optional[float]] = {}
    json_dir = f"xbrl_data_json/{ticker}"

    if not os.path.isdir(json_dir):
        print(f"[WARNING] Directory not found for {ticker}: {json_dir}")
        return None

    for file in os.listdir(json_dir):
        if not (file.endswith(".json") and file.startswith(f"{ticker}_")):
            continue

        filepath = os.path.join(json_dir, file)
        file_date = extract_date_from_filename(file, ticker)
        if file_date is None or file_date.year not in years:
            continue

        date_key = file_date.strftime('%Y-%m-%d')

        # Read JSON
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Error while reading file: {e}")
            stock_data[date_key] = None
            continue

        # If we already stored yf_value, use it
        if "yf_value" in data and data["yf_value"] is not None:
            try:
                stock_data[date_key] = float(data["yf_value"])
                print(f"[DEBUG] Načtena hodnota YF value: {data['yf_value']} pro {date_key}")
            except Exception:
                stock_data[date_key] = None
            continue

        # Otherwise, download and persist it
        try:
            price = yf_download_price(ticker=ticker, date=file_date, file_path=filepath)
            stock_data[date_key] = price
        except Exception as e:
            print(f"[ERROR] Download/write failed for {ticker} {file_date.date()} ({file}): {e}")
            stock_data[date_key] = None

    return stock_data


def yf_download_price(ticker, date, file_path, window_days: int = 3):
    """
    Fetch the Close nearest to `date` within a ±window_days window.
    Fixes TimedeltaIndex .abs() issue by using numpy on the ns values.
    Persists:
      - yf_value
      - yf_value_date (the trading day actually used)
    """
    # Normalize date (tz-naive, midnight)
    date = pd.to_datetime(date)
    try:
        date = date.tz_localize(None)
    except Exception:
        pass
    date = date.normalize()

    # Download a small window around the target date (end is exclusive)
    start_w = date - pd.Timedelta(days=window_days)
    end_w   = date + pd.Timedelta(days=window_days + 1)

    try:
        hist = yf.download(
            tickers=ticker,
            start=start_w,
            end=end_w,
            progress=False,
            auto_adjust=True,
            threads=False
        )
    except Exception as e:
        print(f"[ERROR] yf_download_price download failed for {ticker}: {e}")
        return None

    if hist is None or hist.empty:
        print(f"[WARNING] No data found for {ticker} around {date.date()}")
        return None

    # Robust Close extraction (handles single- and multi-index columns)
    if isinstance(hist.columns, pd.MultiIndex):
        if ('Close', ticker) in hist.columns:
            close = hist[('Close', ticker)]
        elif 'Close' in hist.columns.get_level_values(0):
            close = hist['Close'].iloc[:, 0]
        else:
            close = hist.iloc[:, 0]
    else:
        close = hist.get("Close", hist.iloc[:, 0])

    close = pd.to_numeric(close, errors="coerce").dropna()
    if close.empty:
        print(f"[WARNING] No close series for {ticker} around {date.date()}")
        return None

    # Normalize index to tz-naive dates
    idx = pd.to_datetime(close.index)
    try:
        idx = idx.tz_localize(None)
    except Exception:
        pass
    idx = idx.normalize()
    close.index = idx

    # Find the closest trading day to `date` (no TimedeltaIndex.abs() usage)
    td = close.index - date                        # TimedeltaIndex
    td_ns = td.view('i8')                          # int64 nanoseconds
    td_abs = np.abs(td_ns)                         # absolute distance
    pos = int(np.argmin(td_abs))                   # index of min distance

    picked_date = close.index[pos]
    price = float(close.iloc[pos])

    # Persist into JSON if the file exists
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["yf_value"] = price
            data["yf_value_date"] = picked_date.strftime("%Y-%m-%d")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[ERROR] Failed to update JSON {file_path}: {e}")

    print(f"[INFO] Saved yf_value={price:.2f} (from {picked_date.date()}) for {ticker}")
    return price



# ----------------------------- SEC FETCH (REPORT-DATE-BASED) ----------------
def _get_reporting_date(filing) -> Optional[pd.Timestamp]:
    """
    Robustly obtain the report (period-end) date from a filing object.
    Falls back to filing_date if report date is missing.
    """
    # Try common attribute names for period end
    rd = getattr(filing, "report_date", None) or getattr(filing, "period_of_report", None) \
         or getattr(filing, "period_ended", None)
    if rd is None:
        rd = filing.filing_date
    try:
        return pd.to_datetime(rd)
    except Exception:
        try:
            return pd.to_datetime(filing.filing_date)
        except Exception:
            return None


def SecTools_export_important_data(company, existing_data, year, fetch_yahoo=False, yahoo_vars=None):
    """
    Fetch 10-Q / 10-K around a given calendar year but *store and bucket* by the report date
    (period end). This ensures e.g. "Filed 2018-02-02, Reporting 2017-12-30" is counted under 2017.
    We fetch two windows:
      1) the full year [year-01-01, year-12-31]  (by filing date)
      2) spillover window [year+1-01-01, year+1-01-31] to catch Q4 filed early next year
    """
    print(f"[INFO] Zpracovávám filings pro společnost: {company.cik} ({company.ticker})")

    # Obtain or create in-memory container for this CIK
    company_data = existing_data.companies.get(
        company.cik,
        CompanyIns(company.cik, company.ticker, company.title)
    )

    company_obj = Company(company.cik)

    # Windows by FILING DATE (API filter works on filing date)
    windows = [
        (f"{year-1}-12-01", f"{year+1}-03-25"),
    ]

    all_filings = []
    for start_str, end_str in windows:
        try:
            filings = company_obj.get_filings(form=["10-Q", "10-K"], is_xbrl=True, date=f"{start_str}:{end_str}")
            all_filings.extend(filings)
        except Exception as e:
            print(f"[ERROR] get_filings failed for window {start_str}:{end_str}: {e}")

    # Process each filing: bucket by REPORT DATE year
    for filing in all_filings:
        report_dt = _get_reporting_date(filing)
        if report_dt is None:
            print("[WARNING] Skipping filing without usable date.")
            continue

        # Bucket year uses the report year
        report_year = int(report_dt.year)
        if report_year != int(year):
            # Only keep filings that truly belong to the requested year
            continue

        # Pull XBRL and construct Financials
        xbrl_data = filing.xbrl()
        if xbrl_data is None:
            print("[WARNING] Žádná XBRL data ve filing.")
            continue

        try:
            file_financials = Financials(xbrl_data)
        except Exception as e:
            print(f"[ERROR] Chyba při vytváření objektu Financials: {e}")
            continue

        # Save JSON snapshot using the *report (period-end) date* in the filename
        safe_report_date = report_dt.strftime("%Y-%m-%d")
        json_dir = f"xbrl_data_json/{company.ticker}"
        duplicate_found = False

        # Deduplicate on report date in the JSON directory
        if os.path.exists(json_dir):
            for existing_file in os.listdir(json_dir):
                if existing_file.endswith(".json") and safe_report_date in existing_file:
                    print(f"[DEBUG] JSON pro {company.ticker} (report {safe_report_date}) už existuje, přeskočeno.")
                    duplicate_found = True
                    break
        if duplicate_found:
            # Even if JSON exists, also ensure the in-memory list has it
            if year not in company_data.years:
                company_data.years[year] = []
            exists_in_mem = any(pd.to_datetime(f.date).normalize() == report_dt.normalize()
                                for f in company_data.years[year])
            if not exists_in_mem:
                company_data.years[year].append(CompanyFinancials(report_dt, file_financials, location=None))
            continue

        file_path = save_financials_as_json(file_financials, company.ticker, report_dt)
        if not file_path:
            print("[ERROR] Nepodařilo se uložit JSON.")
            continue

        # Ensure the bucket exists
        if year not in company_data.years:
            company_data.years[year] = []

        # Avoid duplicates in memory by report date
        exists = any(pd.to_datetime(f.date).normalize() == report_dt.normalize()
                     for f in company_data.years[year])
        if not exists:
            company_data.years[year].append(
                CompanyFinancials(report_dt, file_financials, location=file_path)
            )
            print(f"[INFO] Uloženo: {company.ticker} – report {safe_report_date} "
                  f"(filed {getattr(filing, 'filing_date', 'N/A')})")

    return company_data


# ----------------------------- OTHER UTILITIES ------------------------------
def __edgar_API(years, quarter):
    link = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
    get_overview_file(link, years, quarter)


def get_all_current_companies():
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        print("Successfully downloaded indexes of companies.")
        return response.json()
    else:
        print(f"Error while downloading: {response.status_code}")
        return None


def get_overview_file(link, years, quarter):
    result = []
    for current_year in years:
        response = requests.get(link, headers=HEADERS)
        if response.status_code == 200:
            z_file = zipfile.ZipFile(io.BytesIO(response.content))
            print("Zip file downloaded")
            z_file.extractall(f"xbrl_{current_year}_Q{quarter}")
            result.append(z_file)
            return None
        else:
            print("Not able to download zip file")
            return None
    return None


def price_earning_ratio(share_price, earnings_per_share):
    return share_price / earnings_per_share


# ----------------------------- INIT ----------------------------------------
# Set user identity for EDGAR API
set_identity("Alfred AlfredNem@gmail.com")

# Keep the local list of companies fresh
update_company_list()

# Example test case
test = CompanyIns("320193", "AAPL", "Apple Inc.")
saved_data = CompanyData({})
# SecTools_export_important_data(test, saved_data, 2017)
