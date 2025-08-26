import json
import os
from typing import Dict, Optional, Union, Any

import pandas as pd

from helper import find_variables_and_sheets_by_concepts, get_variables_from_json_dict, first_numeric, safe_div, \
    _to_float

# ---- Tags ---------------------------------------------------------------

_NET_INCOME_KEYS = [
    "us-gaap_NetIncomeLoss",
]

_EQUITY_KEYS = [
    "us-gaap_StockholdersEquity",
]

_EPS_KEYS = [
    "us-gaap_StockholdersEquity",
]
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

def calculate_PE(variables: Dict[str, Any], file) -> Optional[float]:
    stock_price = None
    try:
        if file and os.path.exists(file):
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            stock_price = _to_float(data.get("yf_value"))
    except Exception as e:
        print(f"[ERROR] Could not read yf_value from {file}: {e}")
        return None

    if stock_price is None:
        return None
    eps = first_numeric(variables, _EPS_KEYS)
    if eps is None:
        return None
    return safe_div(stock_price, eps) * 100

def calculate_debt_eq_ratio(variables: Dict[str, Any]) -> Optional[float]:
    pass

def calculate_PB(variables: Dict[str, Any]) -> Optional[float]:
    pass

def calculate_PCF(variables: Dict[str, Any]) -> Optional[float]:
    pass


# ---- Main computation ----------------------

def compute_ratios(file: Union[str, Dict], variable_mapping: Dict[str, str], stock_price = None) -> Dict[str, Dict[str, Union[float, str, None]]]:
    """
    Extract base financial variables and compute ratios.
    Save results into 'base' and 'computed' sections in the JSON (if file path given).
    """
    code_variables = list(variable_mapping.values())

    name_variables = find_variables_and_sheets_by_concepts(file, code_variables)
    variables = get_variables_from_json_dict(file, name_variables)

    base: Dict[str, Optional[Union[float, str]]] = {code: val for code, val in variables.items()}
    computed: Dict[str, Optional[float]] = {}

    try:
        computed["ROE"] = calculate_ROE(base)
        computed["P/E"] = calculate_PE(base, file)
    except Exception as e:
        print(f"[ERROR] compute_ratios failed: {e}")

    result = {"base": base, "computed": computed}

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