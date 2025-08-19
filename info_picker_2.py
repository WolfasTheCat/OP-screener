import io
import pickle
import uuid
import zipfile
import json
import os
from datetime import datetime

from urllib import request
from bs4 import BeautifulSoup
import datetime
import dateutil.relativedelta as dr

import pandas as pd
import requests
import yfinance as yf
from typing import Dict

from sec_api import QueryApi, XbrlApi
from sec_edgar_api import EdgarClient
from edgar import *

from indicators import compute_ratios

# File path for storing the company list
FILE_PATH = "company_tickers.json"

# Headers for SEC API requests
HEADERS = {
    'User-Agent': 'EdgarAnalytic/0.1 (AlfredNem@gmail.com)'
}

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

class CompanyIns:
    def __init__(self, cik_str, ticker, title):
        self.cik = cik_str
        self.ticker = ticker
        self.title = title
        self.years = {}


class CompanyFinancials:
    def __init__(self, date, filling, location=None):
        self.date = date
        self.financials = filling
        self.location = location  # Add this line


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
                        cik_str=v.get("cik") or v.get("cik_str"),  # Handle both naming variations
                        ticker=v["ticker"],
                        title=v["title"]
                    )
                    for k, v in data.items()
                }

        else:
            print("No saved company list found.")


def save_xbrl_to_disk(xbrl_data, ticker, reporting_date):
    """
    Saves XBRL data to disk and returns the file path.

    Args:
        xbrl_data (str or bytes): The raw or serialized XBRL content.
        ticker (str): Stock ticker (used in file naming).
        reporting_date (datetime): Date of the report (used in file naming).

    Returns:
        str: Path to the saved file.
    """
    # Ensure the directory exists
    directory = "xbrl_data"
    os.makedirs(directory, exist_ok=True)

    # Unique filename
    safe_date = reporting_date.strftime("%Y-%m-%d")
    filename = f"{ticker}_{safe_date}_{uuid.uuid4().hex[:8]}.xbrl"
    file_path = os.path.join(directory, filename)

    try:
        # Save as binary if it's raw XML (bytes)
        if isinstance(xbrl_data, bytes):
            with open(file_path, "wb") as f:
                f.write(xbrl_data)
        else:
            # Otherwise treat as string/serializable text
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(xbrl_data))
    except Exception as e:
        print(f"Error saving XBRL file: {e}")
        return None

    return file_path

def save_financials_as_json(financials_file, ticker, reporting_date):
    directory = "xbrl_data_json/"+ticker
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

def get_file_variable(variable, sheet_object, year):
    try:
        df = sheet_object.data

        if df.empty:
            print(f"[WARNING] DataFrame je prázdný pro rok {year}.")
            return None

        # Pokud existuje sloupec "concept", filtruj pryč abstract řádky
        if "concept" in df.columns:
            df = df[~df["concept"].str.contains("Abstract", case=False, na=False)]

        # Standardizace dotazu
        var_norm = variable.strip().lower()

        # Seznam možných variant názvu
        candidate_labels = VARIABLE_ALIASES.get(var_norm, [var_norm])

        # 1. Přesná shoda (case-insensitive)
        for name in candidate_labels:
            for row_label in df.index:
                if row_label.strip().lower() == name:
                    value = df.loc[row_label].dropna().iloc[0]
                    print(f"[DEBUG] Načteno: přesná shoda '{row_label}' → {value}")
                    return value

        # 2. Částečná shoda
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

def download_SP500_tickers():
    # URL request, URL opener, read content
    req = request.Request('http://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    opener = request.urlopen(req)
    content = opener.read().decode()  # Convert bytes to UTF-8

    soup = BeautifulSoup(content, features="lxml")
    tables = soup.find_all('table')  # HTML table we actually need is tables[0]

    external_class = tables[0].findAll('a', {'class': 'external text'})

    tickers = []

    for ext in external_class:
        if not 'reports' in ext:
            tickers.append(ext.string)

    return tickers

def extract_date_from_filename(filename: str, ticker: str) -> Optional[pd.Timestamp]:
    """
    Expected filename pattern: <TICKER>_YYYY-MM-DD_<anything>.json
    Returns pandas.Timestamp if found, else None.
    """
    # Escape ticker for regex and capture YYYY-MM-DD between underscores
    m = re.match(rf"^{re.escape(ticker)}_(\d{{4}}-\d{{2}}-\d{{2}})_.*\.json$", filename)
    if not m:
        return None
    try:
        return pd.to_datetime(m.group(1))
    except Exception:
        return None

#TODO Read values from files or update them if missing -DONE --------- Apply it to main function
def yf_get_stock_data(ticker, start_year, end_year):
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

        #Read JSON
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Error while reading file: {e}")
            stock_data[date_key] = None
            continue

        #Only read
        if "yf_value" in data and data["yf_value"] is not None:
            try:
                stock_data[date_key] = float(data["yf_value"])
                print("[DEBUG] Načtena hodnota YF value: " + str(data["yf_value"]) + " pro " +date_key)
            except Exception:
                stock_data[date_key] = None
            continue

        #Missing - Download them

        try:
            price = yf_download_price(ticker=ticker, date=file_date, file_path=filepath)
            stock_data[date_key] = price
        except Exception as e:
            print(f"[ERROR] Download/write failed for {ticker} {file_date.date()} ({file}): {e}")
            stock_data[date_key] = None
    return stock_data

def yf_download_price(ticker, date, file_path):
    # Ensure date is a pandas.Timestamp
    if not isinstance(date, pd.Timestamp):
        date = pd.to_datetime(date)

    # Download data (Yahoo requires an interval > 0 days, so we fetch 1 day extra)
    hist = yf.download(
        tickers=ticker,
        start=date,
        end=date + pd.Timedelta(days=1),
        progress=False,
        auto_adjust=True
    )

    if hist.empty:
        print(f"[WARNING] No data found for {ticker} on {date.date()}")
        return None

    # Get the close price
    close_price = float(hist["Close"].iloc[0])

    # Ensure the JSON file exists
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return None

    # Load existing JSON
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Insert yf_value
    data["yf_value"] = close_price

    # Save back
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"[INFO] Saved yf_value={close_price} into {file_path}")
    return close_price


"""Main function to check for differences and update the company list."""
def SecTools_export_important_data(company, existing_data, year, fetch_yahoo=False, yahoo_vars=None):
    print(f"[INFO] Zpracovávám filings pro společnost: {company.cik} ({company.ticker})")

    company_data = existing_data.companies.get(
        company.cik,
        CompanyIns(company.cik, company.ticker, company.title)
    )

    company_obj = Company(company.cik)
    filings = company_obj.get_filings(form=["10-Q", "10-K"], is_xbrl=True, date=f"{year}-01-01:{year}-12-31")

    for filing in filings:
        xbrl_data = filing.xbrl()
        if xbrl_data is None:
            print("[WARNING] Žádná XBRL data ve filing.")
            continue

        try:
            file_financials = Financials(xbrl_data)
        except Exception as e:
            print(f"[ERROR] Chyba při vytváření objektu Financials: {e}")
            continue

        reporting_date = filing.filing_date
        safe_date = reporting_date.strftime("%Y-%m-%d")
        json_dir = f"xbrl_data_json/{company.ticker}"
        duplicate_found = False

        # Kontrola na duplicitní JSON
        if os.path.exists(json_dir):
            for existing_file in os.listdir(json_dir):
                if existing_file.endswith(".json") and safe_date in existing_file:
                    print(f"[DEBUG] JSON pro {company.ticker} na {safe_date} už existuje, přeskočeno.")
                    duplicate_found = True
                    break

        if duplicate_found:
            continue  # Přeskoč zbytek a pokračuj dalším filingem

        # Uložení JSON
        file_path = save_financials_as_json(file_financials, company.ticker, reporting_date)
        if not file_path:
            print("[ERROR] Nepodařilo se uložit JSON.")
            continue

        if year not in company_data.years:
            company_data.years[year] = []

        # Kontrola, zda již filing pro tento datum není v paměti
        exists = any(f.date == reporting_date for f in company_data.years[year])
        if not exists:
            company_data.years[year].append(
                CompanyFinancials(reporting_date, file_financials, location=file_path)
            )
            print(f"[INFO] Uloženo: {company.ticker} – {safe_date}")

    return company_data

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


# Set user identity for EDGAR API
set_identity("Alfred AlfredNem@gmail.com")

# Run the update process
update_company_list()

# Example test case
test = CompanyIns("320193", "AAPL", "Apple Inc.")
saved_data = CompanyData({})
#SecTools_export_important_data(test, saved_data)
