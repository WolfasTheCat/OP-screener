import json
import os
from typing import List, Optional, Dict, Union, Tuple, Any

import pandas as pd


def human_format(num: float) -> str:
    """
    Convert a number into human-readable format with suffix K, M, B, T.
    Always keeps 2 decimal places.
    Examples:
        1234 -> "1.23K"
        250000000 -> "250.00M"
        540000000000 -> "540.00B"
        1200000000000 -> "1.20T"
    """
    num = float(num)
    abs_num = abs(num)

    if abs_num >= 1e12:
        return f"{num/1e12:.2f}T"
    elif abs_num >= 1e9:
        return f"{num/1e9:.2f}B"
    elif abs_num >= 1e6:
        return f"{num/1e6:.2f}M"
    elif abs_num >= 1e3:
        return f"{num/1e3:.2f}K"
    else:
        return f"{num:.2f}"

def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).replace(",", "").strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den

def first_numeric(variables: Dict[str, Any], keys: list[str]) -> Optional[float]:
    for k in keys:
        if k in variables:
            v = _to_float(variables.get(k))
            if v is not None:
                return v
    return None

def to_percent(r: Optional[float]) -> Optional[float]:
    return None if r is None else r * 100

def extract_selected_indexes(values):
    """Return a list of Yahoo shortcuts (e.g., ^GSPC, ^DJI) from the dropdown selection."""
    if not values:
        return []
    return [v for v in values if isinstance(v, str) and v.startswith("^")]

def find_variables_and_sheets_by_concepts(
    json_file_or_dict: Union[str, dict],
    concepts: List[str],
    *,
    exclude_abstract: bool = True,
    sheet_order: Tuple[str, ...] = ("balance_sheet", "income", "cashflow")
) -> Dict[str, Optional[Tuple[str, str]]]:
    """
    Resolve many XBRL concepts across ALL statements in a single pass.

    Parameters
    ----------
    json_file_or_dict : str | dict
        Path to the saved filing JSON or an already-loaded dict with keys
        'balance_sheet', 'income', 'cashflow'. Each sheet is a dict-of-dicts
        that reconstructs to a DataFrame with row labels as index and a 'concept' column.
    concepts : list[str]
        Concept IDs to search for (e.g., ["us-gaap:AssetsCurrent", ...]).
        Matching is exact, case-insensitive.
    exclude_abstract : bool
        If True, rows whose 'concept' contains 'Abstract' are ignored.
    sheet_order : tuple[str, ...]
        Priority order when building the lookup and resolving duplicates.
        First occurrence wins.

    Returns
    -------
    dict[str, (sheet_name, variable_name) | None]
        For each requested concept, returns a tuple:
           (sheet_name, variable_name)
        or None if not found in any sheet.

    Notes
    -----
    - This is more efficient than calling a single-concept function repeatedly
      because it parses the JSON and builds the lookup exactly once.
    """

    # --- Load JSON once ---
    if isinstance(json_file_or_dict, str):
        if not os.path.exists(json_file_or_dict):
            raise FileNotFoundError(f"JSON file not found: {json_file_or_dict}")
        with open(json_file_or_dict, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(json_file_or_dict, dict):
        data = json_file_or_dict
    else:
        raise TypeError("`json_file_or_dict` must be a file path (str) or a dict.")

    # Normalize inputs we’ll match against
    wanted = {str(c).strip().lower(): c for c in concepts}  # map normalized -> original
    results: Dict[str, Optional[Tuple[str, str]]] = {c: None for c in concepts}

    # Build a single-pass lookup across all sheets
    concept_lookup: Dict[str, Tuple[str, str]] = {}
    for sheet_key in sheet_order:
        sheet_data = data.get(sheet_key, {})
        if not sheet_data:
            continue

        df = pd.DataFrame.from_dict(sheet_data)
        if df.empty or "concept" not in df.columns:
            continue

        search_df = df
        if exclude_abstract:
            search_df = df[~df["concept"].astype(str).str.contains("Abstract", case=False, na=False)]

        # Record first occurrence only (respecting sheet_order priority)
        for row_label, concept_val in zip(search_df.index, search_df["concept"]):
            c_norm = str(concept_val).strip().lower()
            if c_norm and c_norm not in concept_lookup:
                concept_lookup[c_norm] = (sheet_key, str(row_label))

    # Resolve all requested concepts using the built lookup
    for c_norm, original in wanted.items():
        if c_norm in concept_lookup:
            results[original] = concept_lookup[c_norm]

    return results


def normalize_sheet_key(s: str) -> str:
    """Map user-provided sheet string to canonical JSON key."""
    key = s.strip().lower().replace(" ", "_").replace("-", "_")
    if key.startswith("balance"):
        return "balance_sheet"
    if key.startswith("income"):
        return "income"
    if key.startswith("cash"):
        return "cashflow"
    raise ValueError(f"Unknown sheet '{s}'. Use: balance sheet | income | cashflow")

def get_variables_from_json_dict(
    json_file_or_dict: Union[str, Dict],
    requests: Dict[str, Optional[Tuple[str, str]]],
    *,
    return_with_column: bool = False
) -> Dict[str, Union[Optional[float], Tuple[Optional[float], Optional[str]]]]:
    """
    Extract multiple variables (possibly across different sheets) from a single JSON filing,
    where `requests` is a dict mapping OUT_KEY -> (sheet, variable) | None.

    Example of `requests` (your shape):
        {
          "us-gaap_CashAndCashEquivalentsAtCarryingValue": ("balance_sheet", "Cash and cash equivalents"),
          "us-gaap_OperatingIncomeLoss": ("income", "Operating income"),
          "us-gaap_PaymentsToAcquireAvailableForSaleSecurities": ("cashflow", "Purchases of marketable securities")
        }

    Returns a dict with the SAME KEYS as `requests`:
      - value (float or None), or
      - (value, column) if return_with_column=True, where column is the first non-null column (often a date).

    Notes:
    - Exact row-label match (case-insensitive). No aliases, no partial matches.
    - Sheets accepted (flexible spelling): 'balance sheet' / 'balance_sheet' / 'income' / 'cashflow'
    """

    # --- Load JSON once ---
    if isinstance(json_file_or_dict, str):
        if not os.path.exists(json_file_or_dict):
            raise FileNotFoundError(f"File not found: {json_file_or_dict}")
        with open(json_file_or_dict, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(json_file_or_dict, dict):
        data = json_file_or_dict
    else:
        raise TypeError("`json_file_or_dict` must be a file path (str) or a dict")


    default_val = (None, None) if return_with_column else None

    # Collect which sheets are needed
    needed_sheet_keys = set()
    for pair in requests.values():
        if pair is None:
            continue
        sheet, _ = pair
        try:
            needed_sheet_keys.add(normalize_sheet_key(sheet))
        except ValueError:
            # Invalid sheet label → will yield default later
            continue

    # Build DataFrames for the needed sheets once
    sheet_dfs: Dict[str, pd.DataFrame] = {}
    for sk in needed_sheet_keys:
        sheet_dfs[sk] = pd.DataFrame.from_dict(data.get(sk, {}))

    # Resolve each requested item
    results: Dict[str, Union[Optional[float], Tuple[Optional[float], Optional[str]]]] = {}

    for out_key, pair in requests.items():
        # If request is None -> return default
        if pair is None:
            results[out_key] = default_val
            continue

        sheet, variable = pair

        # Normalize + fetch DF
        try:
            sk = normalize_sheet_key(sheet)
        except ValueError:
            results[out_key] = default_val
            continue

        df = sheet_dfs.get(sk, pd.DataFrame())
        if df.empty:
            results[out_key] = default_val
            continue

        # Exact, case-insensitive match on row label
        target = str(variable).strip().lower()
        match_label = None
        for idx in df.index:
            if str(idx).strip().lower() == target:
                match_label = idx
                break

        if match_label is None:
            results[out_key] = default_val
            continue

        row = df.loc[match_label]
        row_numeric = pd.to_numeric(row, errors="coerce")
        mask = row_numeric.notna()
        if not mask.any():
            results[out_key] = default_val
            continue

        first_col = row_numeric.index[mask][0]
        try:
            value = float(row_numeric.loc[first_col])
        except Exception:
            results[out_key] = default_val
            continue

        results[out_key] = (value, str(first_col)) if return_with_column else value

    return results

