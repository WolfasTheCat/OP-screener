# -*- coding: utf-8 -*-
"""
Created on Sat Apr 27 14:53:53 2024

@author: chodo
"""
# This script uses various APIs (SEC, Yahoo Finance) to fetch financial filings and calculate P/E ratio (Price-Earnings Ratio).
# It includes functions to experiment with SEC EDGAR API data and calculate financial ratios.

from sec_api import QueryApi  # API for querying SEC filings (limited requests)
from sec_api import XbrlApi  # API for parsing XBRL data from SEC filings
import const  # Custom constants file, likely containing the API key

# Import other required modules
from sec_edgar_api import EdgarClient  # Edgar API client for SEC filings
import screener_information_picker as picky  # Custom module to extract specific information from documents
import pickle  # Module for serializing and deserializing Python objects (used for storing data)
import yfinance as yf  # Yahoo Finance API to fetch financial data

# A function to experiment with SEC APIs
def __experimenting():
    # Initialize SEC Query and XBRL APIs using the EDGAR API key
    queryApi = QueryApi(api_key=const.EDGAR_API_KEY)
    xbrlApi = XbrlApi(api_key=const.EDGAR_API_KEY)

    # Define a query to fetch 10-Q filings for Microsoft (MSFT) between 2020 and 2024
    query = {
        "query": "ticker:MSFT AND filedAt:[2020-01-01 TO 2024-12-31] AND formType:\"10-Q\"",
        "from": "0",
        "size": "10",
        "sort": [{"filedAt": {"order": "desc"}}]
    }

    # Fetch filings based on the query
    filings = queryApi.get_filings(query)

    # Use custom function to search for specific information within the fetched filings (such as revenue, gross margin, etc.)
    results = picky.find_info_in_doc(document=filings, find=["revenue", "gross", "margin", "financial", "msft-20240331", "17,080", "778", "cik", "htm"])

    # URL for specific filing (in this case, MSFT's 20240331 filing)
    fil_url = 'https://www.sec.gov/Archives/edgar/data/789019/000095017024048288/msft-20240331.htm'

    # Fetch XBRL (Extensible Business Reporting Language) data from the filing
    xbrl_json = xbrlApi.xbrl_to_json(htm_url=fil_url)

    company_ticker = "MSFT"  # Define the company ticker

    # The XBRL data could be saved as a serialized JSON file for further use (pickle not used here in this snippet).
    # The financial statements like income statement, balance sheet, etc., are extracted from the XBRL data.

# Function to calculate the Price-Earnings (P/E) ratio for a given company
def calculate_PE(company_ticker):
    # Load previously saved XBRL data from the file for the given company
    with open(company_ticker+".json", 'rb') as f:
        xbrl_json = pickle.load(f)  # Load the XBRL JSON data

    # Extract the Earnings Per Share (EPS) data from the income statement
    earning_per_share = xbrl_json["StatementsOfIncome"]["EarningsPerShareDiluted"]

    earnings_data = {"date": [], "value": []}  # Dictionary to store P/E ratio data for all dates
    earnings_data_separated = {}  # Separate dictionary to store P/E ratio per earnings value

    # Loop through each earning period in the earnings data
    for earning in earning_per_share:
        period_start = earning["period"]["startDate"]  # Start date of the period
        period_end = earning["period"]["endDate"]  # End date of the period
        earning_per_period = float(earning["value"])  # Earnings per share value for the period

        earnings_data_separated[earning["value"]] = {"date": [], "value": []}  # Initialize dictionary for the earnings value

        # Fetch the historical stock price data from Yahoo Finance for the company between the start and end date
        data_period = yf.download(company_ticker, start=period_start, end=period_end)

        # Calculate the P/E ratio for each date in the fetched data
        for date in data_period.index:
            close_price = data_period["Close"][date]  # Get the closing stock price
            pe = price_earning_ratio(share_price=close_price, earnings_per_share=earning_per_period)  # Calculate the P/E ratio

            # Store the date and P/E ratio in the dictionary
            earnings_data["date"].append(date)
            earnings_data["value"].append(pe)

            # Store the data for this specific earnings value
            earnings_data_separated[earning["value"]]["date"].append(date)
            earnings_data_separated[earning["value"]]["value"].append(pe)

    # Save the computed P/E ratios into a pickle file for future reference
    with open(company_ticker+"_PE"+".json", 'wb') as f:
        pickle.dump(earnings_data, f)  # Save P/E data
    with open(company_ticker+"D_PE"+".json", 'wb') as f:
        pickle.dump(earnings_data_separated, f)  # Save separated P/E data

# Function to experiment with SEC EDGAR API
def wrapper_sec_edgar_api_experiment():
    # Initialize the SEC EDGAR API client with a user agent (important for API requests)
    edgar = EdgarClient(user_agent="<Sample Company Name> <Admin Contact>@<Sample Company Domain>")

    cik = str(789019)  # Central Index Key (CIK) for Microsoft
    submission = edgar.get_submissions(cik=cik)  # Fetch the submissions for the given CIK

    # Example request to fetch specific financial data from SEC's XBRL API
    edgar.get_frames(taxonomy="us-gaap", tag="AccountsPayableCurrent", unit="USD", year="2019", quarter=1)

    # Example of directly accessing data through SEC's public API (for a specific filing URL)
    import requests
    cik = str(789019)  # CIK for Microsoft
    cik_10digs = ((10-len(cik))*"0") + cik  # Format CIK to 10 digits

    # URLs for accessing submissions, company concept, and company facts
    submissions_history_url = "https://data.sec.gov/submissions/CIK"+cik_10digs+".json"
    companyconcept_url  = "https://data.sec.gov/api/xbrl/companyconcept/CIK"+cik_10digs+"/us-gaap/AccountsPayableCurrent.json"
    companyfacts_url    = "https://data.sec.gov/api/xbrl/companyfacts/CIK"+cik_10digs+".json"

    Year = 2019  # Define the year
    Quartal = 1  # Define the quarter
    CY = "msft-20230331"  # Example Central Year (CY) for the XBRL frame
    frames_url = "https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/CY"+CY+".json"
    frames_url_2 = "https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/CY2019Q1I.json"

    accession_number = "0001193125-24-118081"  # Example accession number of a filing

    # Fetch submission history for the company
    response = requests.get(submissions_history_url, headers={"User-Agent": "Mozilla/5.0"})
    json_response = response.json()  # Parse the response as JSON (10-Q filing data)

    # Search for specific information in the SEC filings using the custom picker module
    results = picky.find_info_in_doc(json_response, find=["CY"])

# Function to calculate the Price-Earnings (P/E) ratio
def price_earning_ratio(share_price, earnings_per_share):
    return share_price / earnings_per_share  # P/E ratio is calculated as share price divided by earnings per share




