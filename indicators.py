import pandas as pd

def get_variable_from_sheet(sheet_data, aliases):
    df = pd.DataFrame.from_dict(sheet_data)
    if df.empty:
        return None
    for alias in aliases:
        for row_label in df.index:
            if row_label.strip().lower() == alias:
                try:
                    return float(df.loc[row_label].dropna().iloc[0])
                except Exception:
                    return None
    return None


def compute_ratios(balance_sheet, income, cashflow):
    ratios = {}

    PE = calculate_PE()
    ROE = calculate_ROE()
    debt_eq = calculate_debt_eq_ratio()
    PCF = calculate_PCF()

    return ratios

def calculate_PE():
    pass

def calculate_ROE():
    pass

def calculate_debt_eq_ratio():
    pass

def calculate_PB():
    pass

def calculate_PCF():
    pass