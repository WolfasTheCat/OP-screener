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

def extract_selected_indexes(values):
    """Return a list of Yahoo shortcuts (e.g., ^GSPC, ^DJI) from the dropdown selection."""
    if not values:
        return []
    return [v for v in values if isinstance(v, str) and v.startswith("^")]

def DT_to_sheet(sheet_like):
    """
    Normalize various inputs into an object with attribute `.data` being a pandas DataFrame.
    Handles:
      - dict (as saved from JSON) -> DataFrame.from_dict(...)
      - DataFrame -> as-is
      - object with `.data` -> use it (and if it's a dict, convert to DF)
      - last resort: try DataFrame(obj), else empty DF
    """
    if sheet_like is None:
        df = pd.DataFrame()
    elif isinstance(sheet_like, pd.DataFrame):
        df = sheet_like
    elif isinstance(sheet_like, dict):
        df = pd.DataFrame.from_dict(sheet_like)
    elif hasattr(sheet_like, "data"):
        raw = getattr(sheet_like, "data")
        if isinstance(raw, pd.DataFrame):
            df = raw
        elif isinstance(raw, dict):
            df = pd.DataFrame.from_dict(raw)
        else:
            # Fallback if raw is list-like or something convertible
            try:
                df = pd.DataFrame(raw)
            except Exception:
                df = pd.DataFrame()
    else:
        try:
            df = pd.DataFrame(sheet_like)
        except Exception:
            df = pd.DataFrame()

    return type("Sheet", (object,), {"data": df})()