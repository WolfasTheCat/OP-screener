import json
import os
from typing import Dict, Optional, Union, Any

import pandas as pd

from helper import find_variables_and_sheets_by_concepts, get_variables_from_json_dict, first_numeric, safe_div, _to_float

# ---- Tags ---------------------------------------------------------------
GAAP_PREFIXES = ("us-gaap_",)  # extend if you use others

_REQUIRED_FOR_COMPUTED = {
    # ROE
    "us-gaap_NetIncomeLoss",
    "us-gaap_StockholdersEquity",

    # P/E (reported EPS first)
    "us-gaap_EarningsPerShareDiluted",
    "us-gaap_EarningsPerShareBasic",
    "us-gaap_IncomeLossFromContinuingOperationsPerDilutedShare",
    "us-gaap_IncomeLossFromContinuingOperationsPerBasicShare",

    # P/E fallback EPS = NI / Weighted Avg Shares
    "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
    "us-gaap_WeightedAverageNumberOfSharesOutstandingDiluted",   # alt
    "us-gaap_WeightedAverageNumberOfSharesOutstandingBasic",
    "us-gaap_WeightedAverageNumberOfSharesOutstanding",          # alt

    # P/FCF needs CFO, CapEx, and shares
    "us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    "us-gaap_NetCashProvidedByUsedInOperatingActivities",  # alt (some filers use this)
    "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
}

_NET_INCOME_KEYS = [
    "us-gaap_NetIncomeLoss",
]

_EQUITY_KEYS = [
    "us-gaap_StockholdersEquity",
]

# Preferred EPS tags, then continuing-ops variants as fallback
_EPS_KEYS = [
    "us-gaap_EarningsPerShareDiluted",
    "us-gaap_EarningsPerShareBasic",
    "us-gaap_IncomeLossFromContinuingOperationsPerDilutedShare",
    "us-gaap_IncomeLossFromContinuingOperationsPerBasicShare",
]

# Weighted-average share count (diluted & basic) — multiple common variants
_SHARES_DILUTED_KEYS = [
    "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
    "us-gaap_WeightedAverageNumberOfSharesOutstandingDiluted",
    "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding"
]
_SHARES_BASIC_KEYS = [
    "us-gaap_WeightedAverageNumberOfSharesOutstandingBasic",
    "us-gaap_WeightedAverageNumberOfSharesOutstanding",
]

# CFO and CapEx for FCF
_CFO_KEYS = [
    "us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    "us-gaap_NetCashProvidedByUsedInOperatingActivities",
]
_CAPEX_KEYS = [
    "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
]


def _read_yf_value_from_any(file_or_json: Union[str, Dict, None]) -> Optional[float]:
    """
    Try to read 'yf_value' either from:
      - dict (already loaded JSON), or
      - JSON file path.
    """
    if isinstance(file_or_json, dict):
        return _to_float(file_or_json.get("yf_value"))
    if isinstance(file_or_json, str) and os.path.exists(file_or_json):
        try:
            with open(file_or_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _to_float(data.get("yf_value"))
        except Exception:
            return None
    return None

# ---- Variables ---------------------------------------
def calculate_EPS(variables: Dict[str, Any], stock_price=None) -> Optional[float]:
    """
    EPS preference:
      1) Reported EPS (diluted → basic → continuing-ops variants)
      2) Fallback: NetIncomeLoss / WeightedAverageShares (diluted → basic)
    """
    # 1) Reported EPS if present
    eps = first_numeric(variables, _EPS_KEYS)
    if eps is not None:
        return eps

    # 2) Fallback: NI / shares (prefer diluted)
    net_income = first_numeric(variables, _NET_INCOME_KEYS)

    # Try diluted shares
    shares = first_numeric(variables, _SHARES_DILUTED_KEYS)
    eps = safe_div(net_income, shares)
    if eps is not None:
        return eps

    # Try basic shares
    shares = first_numeric(variables, _SHARES_BASIC_KEYS)
    eps = safe_div(net_income, shares)
    return eps


# ---- Indicators ---------------------------------------
def calculate_ROE(variables: Dict[str, Any]) -> Optional[float]:
    """
    ROE = Net Income / Shareholders' Equity  (end-of-period only)

    Looks up values from `variables` using common US-GAAP keys.
    Returns None if inputs are missing or denominator is zero.
    """
    net_income = first_numeric(variables, _NET_INCOME_KEYS)
    equity_end = first_numeric(variables, _EQUITY_KEYS)
    return safe_div(net_income, equity_end) * 100


def calculate_PE(variables: Dict[str, Any], file_or_json: Union[str, Dict, None] = None, stock_price: Optional[float] = None) -> Optional[float]:
    """
    P/E = Price per Share / EPS (trailing or period EPS)
    - Prefers an explicitly provided `stock_price`
    - Otherwise tries to read 'yf_value' from `file_or_json` (dict or path)
    """
    # 1) Price
    price = _to_float(stock_price) if stock_price is not None else None
    if price is None:
        price = _read_yf_value_from_any(file_or_json)
    if price is None:
        return None

    # 2) EPS (use reported if present; otherwise NI / WAvg shares)
    eps = first_numeric(variables, _EPS_KEYS)
    if eps is None:
        eps = calculate_EPS(variables)

    return safe_div(price, eps)


def calculate_PFCF(variables: Dict[str, Any], file_or_json: Union[str, Dict, None] = None, stock_price: Optional[float] = None) -> Optional[float]:
    """
    P/FCF = Price per Share / (Free Cash Flow per Share)
    FCF = CFO - CapEx
    """
    # 1) Price
    price = _to_float(stock_price) if stock_price is not None else None
    if price is None:
        price = _read_yf_value_from_any(file_or_json)
    if price is None:
        return None

    # 2) FCF = CFO - CapEx
    cfo = first_numeric(variables, _CFO_KEYS)
    capex = first_numeric(variables, _CAPEX_KEYS)
    if cfo is None or capex is None:
        return None
    fcf = cfo - capex

    # 3) Per share (prefer diluted shares; fallback basic)
    shares = first_numeric(variables, _SHARES_DILUTED_KEYS)
    if shares is None:
        shares = first_numeric(variables, _SHARES_BASIC_KEYS)
    fcf_ps = safe_div(fcf, shares)
    if fcf_ps is None:
        return None

    # 4) Ratio
    return safe_div(price, fcf_ps)


def calculate_debt_eq_ratio(variables: Dict[str, Any]) -> Optional[float]:
    pass


def calculate_PB(variables: Dict[str, Any]) -> Optional[float]:
    pass


def calculate_PCF(variables: Dict[str, Any]) -> Optional[float]:
    pass


# ---- Main computation ----------------------
def compute_ratios(file: Union[str, Dict], variable_mapping: Dict[str, str], stock_price: Optional[float] = None) -> Dict[str, Dict[str, Union[float, str, None]]]:
    # 1) Only GAAP-like codes go to 'base'
    user_codes = set(variable_mapping.values())
    gaap_codes = {c for c in user_codes if isinstance(c, str) and c.startswith(GAAP_PREFIXES)}

    # Add internal deps for computed metrics (still GAAP tags)
    code_variables = list(gaap_codes | _REQUIRED_FOR_COMPUTED)

    name_variables = find_variables_and_sheets_by_concepts(file, code_variables)
    variables = get_variables_from_json_dict(file, name_variables)

    # 2) Base contains ONLY GAAP-like keys we requested above
    base: Dict[str, Optional[Union[float, str]]] = {code: val for code, val in variables.items()}

    # 3) Computed contains ratios
    computed: Dict[str, Optional[float]] = {}
    try:
        computed["ROE"] = calculate_ROE(base)
        computed["P/E"] = calculate_PE(base, file_or_json=file, stock_price=stock_price)
        computed["P/FCF"] = calculate_PFCF(base, file_or_json=file, stock_price=stock_price)
    except Exception as e:
        print(f"[ERROR] compute_ratios failed: {e}")

    result = {"base": base, "computed": computed}

    # Persist
    if isinstance(file, str) and os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["base"] = base
            data["computed"] = computed
            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[ERROR] Failed to persist base/computed into {file}: {e}")

    return result
