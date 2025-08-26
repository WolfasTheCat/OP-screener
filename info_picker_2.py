from io import StringIO, BytesIO
import uuid
import zipfile
import json
import os
import re
import time
from urllib import request as urllib_request

import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pandas as pd
import requests
import yfinance as yf
from typing import Dict, Optional, Tuple, List, Union
from edgar import *
from indicators import compute_ratios

# ----------------------------- CONSTANTS ------------------------------------

FILE_PATH = "company_tickers.json"

HEADERS = {
    # Use a realistic desktop UA – many sites (incl. Wikipedia) block default Python UAs.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Aliases to locate variables in XBRL tables (kept for fallback-only)
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

# Cache for index tickers (seconds)
INDEX_CACHE_SECONDS = 24 * 3600
CACHE_DIR = ".cache_index_lists"
os.makedirs(CACHE_DIR, exist_ok=True)


# ----------------------------- DATA CLASSES ---------------------------------
class CompanyIns:
    def __init__(self, cik_str, ticker, title):
        self.cik = cik_str
        self.ticker = ticker
        self.title = title
        self.years = {}  # dict[int, List[CompanyFinancials]]


class CompanyFinancials:
    def __init__(self, date, filling, location=None, json_data: Optional[dict] = None):
        self.date = date                    # report date (period end)
        self.financials = filling           # edgar.Financials or a wrapper
        self.location = location            # path to saved JSON snapshot
        self.json_data = json_data          # cached JSON dict (if available)


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


def save_financials_as_json(
    financials_file,
    ticker: str,
    reporting_date: datetime,
    *,
    out_dir: str = "xbrl_data_json",
    variable_mapping: dict | None = None
) -> str:
    """
    Serialize parsed financial statements into a JSON file.
    Optionally computes 'base' and 'computed' ratios using `variable_mapping`.
    """
    try:
        safe_date = reporting_date.strftime("%Y-%m-%d")
    except Exception:
        try:
            safe_date = str(reporting_date)
        except Exception:
            safe_date = "unknown-date"

    os.makedirs(os.path.join(out_dir, ticker), exist_ok=True)
    file_path = os.path.join(out_dir, ticker, f"{ticker}_{safe_date}.json")

    try:
        balance_sheet_df = financials_file.get_balance_sheet().data
        income_df = financials_file.get_income_statement().data
        cashflow_df = financials_file.get_cash_flow_statement().data

        data = {
            "balance_sheet": balance_sheet_df.to_dict(),
            "income": income_df.to_dict(),
            "cashflow": cashflow_df.to_dict(),
            "date": safe_date,
            "ticker": ticker
        }

        if variable_mapping:
            ratios = compute_ratios(data, variable_mapping)
            data.update(ratios)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        return file_path

    except Exception as e:
        print(f"[ERROR] save_financials_as_json failed for {ticker} {safe_date}: {e}")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass
        return file_path


# ----------------------------- VARIABLE EXTRACT -----------------------------
def _load_json_any(file_or_json: Union[str, dict, None]) -> Optional[dict]:
    """Load JSON dict from a filepath or return the dict if already provided."""
    if file_or_json is None:
        return None
    if isinstance(file_or_json, dict):
        return file_or_json
    if isinstance(file_or_json, str):
        try:
            with open(file_or_json, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to read JSON '{file_or_json}': {e}")
            return None
    return None


def get_file_variable(variable_key: str, file_or_json: Union[str, dict, None], year: Optional[int] = None):
    """
    Prefer values from JSON sections 'base' / 'computed'.
    - If `variable_key` starts with 'us-gaap' → search in base[variable_key]
    - Otherwise → search in computed[variable_key]
    Falls back to legacy .data scanning only if JSON is not available.
    """
    data = _load_json_any(file_or_json)

    key = variable_key.strip()
    # Preferred path: JSON with 'base'/'computed'
    if isinstance(data, dict) and ("base" in data or "computed" in data):
        is_usgaap = key.lower().startswith("us-gaap")
        section = "base" if is_usgaap else "computed"
        bucket = data.get(section, {})

        if key in bucket:
            try:
                return float(bucket[key])
            except Exception:
                return bucket[key]

        other = "computed" if section == "base" else "base"
        if key in data.get(other, {}):
            try:
                return float(data[other][key])
            except Exception:
                return data[other][key]

        print(f"[DEBUG] Key '{key}' not present in '{section}' nor '{other}'.")
        return None

    # Fallback: try object with .data (kept for backward compatibility)
    try:
        df = getattr(file_or_json, "data", None)
        if df is None:
            if data is None:
                print("[WARNING] No JSON nor .data DataFrame available; cannot resolve variable.")
            return None

        if df.empty:
            print(f"[WARNING] DataFrame is empty for year {year}.")
            return None

        var_norm = key.lower()
        try:
            candidate_labels = VARIABLE_ALIASES.get(var_norm, [var_norm])
        except NameError:
            candidate_labels = [var_norm]

        # exact
        for name in candidate_labels:
            for row_label in df.index:
                if str(row_label).strip().lower() == name:
                    value = df.loc[row_label].dropna().iloc[0]
                    try:
                        return float(value)
                    except Exception:
                        return value

        # partial
        for name in candidate_labels:
            for row_label in df.index:
                if name in str(row_label).strip().lower():
                    value = df.loc[row_label].dropna().iloc[0]
                    try:
                        return float(value)
                    except Exception:
                        return value

        print(f"[DEBUG] (fallback) Variable '{variable_key}' not found.")
        return None

    except Exception as e:
        print(f"[ERROR] Error while extracting variable (fallback): {e}")
        return None


# ----------------------------- COMPANY LIST MGMT ----------------------------
def download_company_tickers():
    """Fetch the latest company tickers list from SEC."""
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers={"User-Agent": "EdgarAnalytic/0.1 (contact@example.com)"})
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
def _load_cached_list(cache_name: str) -> Optional[List[str]]:
    """Load cached tickers if not stale; else None."""
    path = os.path.join(CACHE_DIR, cache_name)
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if (time.time() - mtime) > INDEX_CACHE_SECONDS:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cached_list(cache_name: str, tickers: List[str]) -> None:
    """Save tickers to cache."""
    path = os.path.join(CACHE_DIR, cache_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tickers, f, indent=2)
    except Exception:
        pass


def _fetch_html(url: str) -> Optional[str]:
    """
    Fetch HTML with hardened headers to avoid 403.
    Returns decoded text or None.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200 and resp.text:
            return resp.text
        print(f"[INDEX] HTTP {resp.status_code} on {url}")
        return None
    except Exception as e:
        print(f"[INDEX] Request failed for {url}: {e}")
        return None


def _parse_sp500_from_html(html: str) -> List[str]:
    """
    Extract S&P 500 symbols from Wikipedia HTML.
    Strategy:
      - Try pandas.read_html and pick the first table containing 'Symbol' column.
      - Fallback to BeautifulSoup parsing of <table> rows.
    """
    # Try pandas first – resilient to minor markup changes.
    try:
        tables = pd.read_html(html)
        for df in tables:
            cols = [str(c).strip().lower() for c in df.columns]
            if any("symbol" in c for c in cols):
                syms = df[[c for c in df.columns if "symbol" in str(c).lower()][0]].astype(str).str.strip().tolist()
                syms = [s.replace(".", "-") for s in syms if s and s != "nan"]
                return syms
    except Exception:
        pass

    # Fallback: BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    for t in tables:
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if any("symbol" in h for h in headers):
            syms = []
            for row in t.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if not cells:
                    continue
                # symbol usually in column 0 or 1
                for c in cells[:2]:
                    if c and len(c) <= 6 and c.isupper():
                        syms.append(c.replace(".", "-"))
                        break
            return [s for s in syms if s]
    return []


def _parse_dji_from_html(html: str) -> List[str]:
    """
    Extract DJI components from Wikipedia HTML using the same approach.
    """
    # pandas first
    try:
        tables = pd.read_html(StringIO(html))
        for df in tables:
            cols = [str(c).strip().lower() for c in df.columns]
            if any("symbol" in c for c in cols):
                syms = df[[c for c in df.columns if "symbol" in str(c).lower()][0]].astype(str).str.strip().tolist()
                syms = [s.replace(".", "-") for s in syms if s and s != "nan"]
                return syms
    except Exception:
        pass

    # soup fallback
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    for t in tables:
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if any("symbol" in h for h in headers):
            syms = []
            for row in t.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if not cells:
                    continue
                for c in cells[:2]:
                    if c and len(c) <= 6 and c.isupper():
                        syms.append(c.replace(".", "-"))
                        break
            return [s for s in syms if s]
    return []


def download_SP500_tickers() -> List[str]:
    """
    Get S&P 500 constituents.
    - Uses strong headers to avoid 403.
    - Caches results for 24h.
    - Returns [] on failure (never raises), so UI can degrade gracefully.
    """
    cache_name = "sp500.json"
    cached = _load_cached_list(cache_name)
    if cached:
        return cached

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = _fetch_html(url)
    if not html:
        print("[INDEX] Failed to fetch S&P 500 page (403 or network issue). Returning empty list.")
        return []

    syms = _parse_sp500_from_html(html)
    # Final clean-up: some sources use dots for class A/B shares – Yahoo prefers dashes.
    syms = [s.replace(".", "-") for s in syms]
    if syms:
        _save_cached_list(cache_name, syms)
    return syms


def download_DJI_tickers() -> List[str]:
    """
    Get Dow Jones Industrial Average constituents.
    Same approach as S&P 500 and cached for 24h.
    """
    cache_name = "dji.json"
    cached = _load_cached_list(cache_name)
    if cached:
        return cached

    url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
    html = _fetch_html(url)
    if not html:
        print("[INDEX] Failed to fetch DJI page (403 or network issue). Returning empty list.")
        return []

    syms = _parse_dji_from_html(html)
    syms = [s.replace(".", "-") for s in syms]
    if syms:
        _save_cached_list(cache_name, syms)
    return syms


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
    Extract the YYYY-MM-DD date from filenames like:
      - <TICKER>_YYYY-MM-DD.json
      - <TICKER>_YYYY-MM-DD_<anything>.json
    Returns pandas.Timestamp if found, else None.
    """
    m = re.match(rf"^{re.escape(ticker)}_(\d{{4}}-\d{{2}}-\d{{2}})(?:_.*)?\.json$", filename)
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
                print(f"[DEBUG] Loaded existing YF value: {data['yf_value']} for {date_key}")
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
    date = pd.to_datetime(date)
    try:
        date = date.tz_localize(None)
    except Exception:
        pass
    date = date.normalize()

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

    idx = pd.to_datetime(close.index)
    try:
        idx = idx.tz_localize(None)
    except Exception:
        pass
    idx = idx.normalize()
    close.index = idx

    td = close.index - date
    td_ns = td.view('i8')
    td_abs = np.abs(td_ns)
    pos = int(np.argmin(td_abs))

    picked_date = close.index[pos]
    price = float(close.iloc[pos])

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


# ----------------------------- SEC FETCH ------------------------------------
def _get_reporting_date(filing) -> Optional[pd.Timestamp]:
    """Try to obtain the report (period-end) date from a filing object."""
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


def SecTools_export_important_data(company, existing_data, year, fetch_yahoo=False, yahoo_vars=None, mapping_variables=None):
    """
    Fetch 10-Q / 10-K around a given calendar year but *store and bucket* by the report date
    (period end).
    """
    print(f"[INFO] Zpracovávám filings pro společnost: {company.cik} ({company.ticker})")

    company_data = existing_data.companies.get(
        company.cik,
        CompanyIns(company.cik, company.ticker, company.title)
    )

    company_obj = Company(company.cik)

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

    for filing in all_filings:
        report_dt = _get_reporting_date(filing)
        if report_dt is None:
            print("[WARNING] Skipping filing without usable date.")
            continue

        report_year = int(report_dt.year)
        if report_year != int(year):
            continue

        xbrl_data = filing.xbrl()
        if xbrl_data is None:
            print("[WARNING] Žádná XBRL data ve filing.")
            continue

        try:
            file_financials = Financials(xbrl_data)
        except Exception as e:
            print(f"[ERROR] Chyba při vytváření objektu Financials: {e}")
            continue

        safe_report_date = report_dt.strftime("%Y-%m-%d")
        json_dir = f"xbrl_data_json/{company.ticker}"
        duplicate_found = False

        if os.path.exists(json_dir):
            for existing_file in os.listdir(json_dir):
                if existing_file.endswith(".json") and safe_report_date in existing_file:
                    print(f"[DEBUG] JSON pro {company.ticker} (report {safe_report_date}) už existuje, přeskočeno.")
                    duplicate_found = True
                    break
        if duplicate_found:
            if year not in company_data.years:
                company_data.years[year] = []
            exists_in_mem = any(pd.to_datetime(f.date).normalize() == report_dt.normalize()
                                for f in company_data.years[year])
            if not exists_in_mem:
                company_data.years[year].append(CompanyFinancials(report_dt, file_financials, location=None))
            continue

        file_path = save_financials_as_json(file_financials, company.ticker, report_dt, variable_mapping=mapping_variables)
        if not file_path:
            print("[ERROR] Nepodařilo se uložit JSON.")
            continue

        if year not in company_data.years:
            company_data.years[year] = []

        exists = any(pd.to_datetime(f.date).normalize() == report_dt.normalize()
                     for f in company_data.years[year])
        if not exists:
            company_data.years[year].append(
                CompanyFinancials(report_dt, file_financials, location=file_path, json_data=None)
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
            z_file = zipfile.ZipFile(BytesIO(response.content))
            print("Zip file downloaded")
            z_file.extractall(f"xbrl_{current_year}_Q{quarter}")
            result.append(z_file)
            return None
        else:
            print("Not able to download zip file")
            return None
    return None


# ----------------------------- INIT ----------------------------------------
set_identity("Alfred AlfredNem@gmail.com")
update_company_list()

# Example:
# test = CompanyIns("320193", "AAPL", "Apple Inc.")
# saved_data = CompanyData({})
# SecTools_export_important_data(test, saved_data, 2017)
