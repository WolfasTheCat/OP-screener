import io
import pickle
import uuid
import zipfile
import json
import os
import requests
import yfinance as yf
from typing import Dict
from sec_api import QueryApi, XbrlApi
from sec_edgar_api import EdgarClient
import const
import screener_information_picker as picky
from edgar import *

# File path for storing the company list
FILE_PATH = "company_tickers.json"

# Headers for SEC API requests
HEADERS = {
    'User-Agent': 'EdgarAnalytic/0.1 (AlfredNem@gmail.com)'
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
            "balance_sheet": financials_file.balance_sheet.data.to_dict(),
            "income": financials_file.income.data.to_dict(),
            "cashflow": financials_file.cashflow.data.to_dict(),
            "date": safe_date
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving financials JSON: {e}")
        return None

    return file_path

VARIABLE_ALIASES = {
    "total assets": ["total assets", "assets"],
    "total liabilities": ["total liabilities", "liabilities"],
    "cash": ["cash", "cash and cash equivalents at carrying value"]
}

def get_file_variable(variable, sheet_object, year):
    try:
        df = sheet_object.data

        if df.empty:
            print(f"[WARNING] DataFrame je prázdný pro rok {year}.")
            return None

        # Standardizace dotazu
        var_norm = variable.strip().lower()

        # Seznam možných variant názvu
        candidate_labels = VARIABLE_ALIASES.get(var_norm, [var_norm])

        # 1. Přesná shoda (case-insensitive)
        for name in candidate_labels:
            for row_label in df.index:
                if row_label.strip().lower() == name:
                    print(f"[DEBUG] Načteno: přesná shoda '{row_label}'")
                    return df.loc[row_label].dropna().iloc[0]

        # 2. Částečná shoda
        for name in candidate_labels:
            for row_label in df.index:
                if name in row_label.strip().lower():
                    print(f"[DEBUG] Načteno: částečná shoda '{row_label}'")
                    return df.loc[row_label].dropna().iloc[0]

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

def SecTools_export_important_data(company, existing_data):
    print(f"[INFO] Zpracovávám filings pro společnost: {company.cik} ({company.ticker})")

    company_data = existing_data.companies.get(
        company.cik,
        CompanyIns(company.cik, company.ticker, company.title)
    )

    company_obj = Company(company.cik)
    filings = company_obj.get_filings(form=["10-Q", "10-K"], is_xbrl=True, date="2017-01-01:2023-12-31")

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
        year = reporting_date.year
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
