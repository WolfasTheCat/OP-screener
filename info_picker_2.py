import io
import pickle
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
    def __init__(self, date, filling):
        self.date = date
        self.financials = filling


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

def get_sheet_variable(variable,sheet):
    try:
        df = sheet.data
        labels = sheet.labels

        # Look for the label 'Total assets' (case insensitive)
        for i, label in enumerate(labels):
            if label.strip().lower() == variable.strip().lower():
                variable_row = df.iloc[i]
                first_value = variable_row.dropna().iloc[0]  # Get the first non-null value
                return first_value  # Return just the number, e.g., 190000

        print("variable not found in sheet.")
        return None
    except Exception as e:
        print(f"Error while extracting variable: {e}")
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
    print(f"Processing filings for company: {company.cik}")

    company_data = existing_data.companies.get(company.cik, CompanyIns(company.cik, company.ticker, company.title))

    company_obj = Company(company.cik)
    filings = company_obj.get_filings(form=["10-Q", "10-K"], is_xbrl=True, date="2020-01-01:2022-01-01")

    for filing in filings:
        # Parse the XBRL data
        xbrl_data = filing.xbrl()
        if xbrl_data is None:
            continue

        # Access the financial statements
        filing_financials = Financials(xbrl_data)

        # Retrieve the reporting date
        reporting_date = filing.filing_date
        year = reporting_date.year

        # Store the balance sheet data
        if year not in company_data.years:
            company_data.years[year] = []

        # Check if this reporting date already exists
        exists = any(
            financial.date == reporting_date
            for financial in company_data.years[year]
        )

        if not exists:
            company_data.years[year].append(
                CompanyFinancials(reporting_date, filing_financials)
            )

    return company_data


def SecTools_all_fillings_for_companies(list_all_companies, filling_type):
    companies_data = CompanyData(list_all_companies)
    return 0


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
        else:
            print("Not able to download zip file")
            return None


def expert():
    all_companies = get_all_current_companies()
    if all_companies:
        SecTools_all_fillings_for_companies(all_companies, "10-Q")


def price_earning_ratio(share_price, earnings_per_share):
    return share_price / earnings_per_share


def calculate_PE(company_ticker):
    with open(company_ticker + ".json", 'rb') as f:
        xbrl_json = pickle.load(f)

    earning_per_share = xbrl_json["StatementsOfIncome"]["EarningsPerShareDiluted"]
    earnings_data = {"date": [], "value": []}
    earnings_data_separated = {}

    for earning in earning_per_share:
        period_start = earning["period"]["startDate"]
        period_end = earning["period"]["endDate"]
        earning_per_period = float(earning["value"])

        earnings_data_separated[earning["value"]] = {"date": [], "value": []}

        data_period = yf.download(company_ticker, start=period_start, end=period_end)

        for date in data_period.index:
            close_price = data_period["Close"][date]
            pe = price_earning_ratio(close_price, earning_per_period)

            earnings_data["date"].append(date)
            earnings_data["value"].append(pe)
            earnings_data_separated[earning["value"]]["date"].append(date)
            earnings_data_separated[earning["value"]]["value"].append(pe)

    with open(company_ticker + "_PE" + ".json", 'wb') as f:
        pickle.dump(earnings_data, f)
    with open(company_ticker + "D_PE" + ".json", 'wb') as f:
        pickle.dump(earnings_data_separated, f)


# Set user identity for EDGAR API
set_identity("Alfred AlfredNem@gmail.com")

# Run the update process
update_company_list()

# Example test case
test = CompanyIns("320193", "AAPL", "Apple Inc.")
saved_data = CompanyData({})
#SecTools_export_important_data(test, saved_data)

expert()
