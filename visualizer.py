import os
import json
import sys
from datetime import datetime
from typing import List, Optional, Dict
import dash_bootstrap_components as dbc

import dash
import pandas as pd
from dash import dcc, html, dash_table, callback_context, no_update
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go

import info_picker_2
from helper import human_format, extract_selected_indexes

# ----------------------------- CONSTANTS -----------------------------------
# GAAP/base variables only (mapped to us-gaap codes)
MAPPING_VARIABLE: Dict[str, str] = {
    "Total assets": "us-gaap_Assets",
    "Total liabilities": "us-gaap_Liabilities",
    "Cash": "us-gaap_CashAndCashEquivalentsAtCarryingValue",
    "Net income": "us-gaap_NetIncomeLoss",
    "Total shareholders’ equity": "us-gaap_StockholdersEquity",
    "Shares diluted": "us-gaap_EarningsPerShareDiluted",
    "Shares basic": "us-gaap_EarningsPerShareBasic",
}

# Computed-only variables (never stored in 'base', only in 'computed')
RATIO_VARIABLES: List[str] = [
    "ROE",
    "P/E",
    "P/FCF",
    "P/CF",
    "D/E",
    "Pretax Profit Margin"
]

# Special variables (neither GAAP nor ratio) read directly from JSON
SPECIAL_VARIABLES: List[str] = [
    "Stock value",  # reads json["yf_value"]
]

# Combined for UI dropdowns
VARIABLES: List[str] = list(MAPPING_VARIABLE.keys()) + RATIO_VARIABLES + SPECIAL_VARIABLES

YEAR_RANGE = {"start": 2018, "end": datetime.now().year - 7}

PRESET_SOURCES = {
    "sp500": {
        "label": "S&P 500",
        "loader": info_picker_2.download_SP500_tickers,
        "shortcut": "^SPX"  # or ^GSPC if you prefer
    },
    "dowjones": {
        "label": "Dow Jones Industrial Average",
        "loader": info_picker_2.download_DJI_tickers,
        "shortcut": "^DJI"
    }
}

# ----------------------------- LOAD COMPANY DATA ---------------------------
companies = info_picker_2.CompanyData()
companies.load_saved_companies()
TICKER_TO_CIK = {v.ticker.upper(): k for k, v in companies.companies.items()}


# ----------------------------- HELPERS -------------------------------------
def _to_sheet(sheet_like):
    """Wrap any input so that `.data` is a DataFrame."""
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


def build_table_variable_options():
    """Options for the summary table variable picker (base + ratios + specials)."""
    final = list(MAPPING_VARIABLE.keys()) + RATIO_VARIABLES + SPECIAL_VARIABLES
    return [{"label": v, "value": v} for v in final]


def _read_json(filepath: str) -> Optional[dict]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read JSON {filepath}: {e}")
        return None


def extract_from_base_or_computed(json_dict: dict, human_variable: str) -> Optional[float]:
    """
    Read a variable from JSON 'base'/'computed' or (for specials) from top-level JSON.
    - GAAP variables: read base[us-gaap_*] using MAPPING_VARIABLE.
    - Ratios (ROE, P/E): read from computed[<ratio>].
    - Special "Stock value": read json["yf_value"].
    """
    if not isinstance(json_dict, dict):
        return None
    base = json_dict.get("base", {}) or {}
    computed = json_dict.get("computed", {}) or {}

    # Ratios → computed only
    if human_variable in RATIO_VARIABLES:
        val = computed.get(human_variable)
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    # Specials
    if human_variable == "Stock value":
        try:
            val = json_dict.get("yf_value")
            return float(val) if val is not None else None
        except Exception:
            return None

    # GAAP variables → base via code
    code = MAPPING_VARIABLE.get(human_variable)
    if code and code in base:
        try:
            return float(base[code])
        except Exception:
            return None

    return None


# ----------------------------- SUMMARY TABLE --------------------------------
def load_summary_table(selected_variables=None):
    if not selected_variables:
        vars_to_use = list(VARIABLES)
    else:
        # allow GAAP-mapped, ratios, and specials
        vars_to_use = [v for v in selected_variables if (
            v in MAPPING_VARIABLE or v in RATIO_VARIABLES or v in SPECIAL_VARIABLES
        )]
        if not vars_to_use:
            vars_to_use = list(VARIABLES)

    records = []
    for cik, company in companies.companies.items():
        ticker, name = company.ticker, company.title
        json_dir = f"xbrl_data_json/{ticker}"
        if not os.path.exists(json_dir):
            continue

        for file in os.listdir(json_dir):
            if not file.endswith(".json"):
                continue
            filepath = os.path.join(json_dir, file)
            data = _read_json(filepath)
            if not data:
                continue
            report_date = pd.to_datetime(data.get("date", None))
            if not report_date:
                continue

            row = {"CIK": cik, "Ticker": ticker, "Company": name, "Date": report_date.strftime("%Y-%m-%d")}
            for var in vars_to_use:
                val = extract_from_base_or_computed(data, var)
                try:
                    row[var] = int(val) if val is not None and float(val).is_integer() else val
                except Exception:
                    row[var] = val
            records.append(row)

    columns = ["CIK", "Ticker", "Company", "Date"] + vars_to_use
    df = pd.DataFrame(records, columns=columns)
    if not df.empty:
        df.sort_values(["Company", "Date"], inplace=True)
    else:
        print("[WARNING] No records loaded for summary.")
    return df


# ----------------------------- GRAPH GENERATION -----------------------------
def generate_graph(selected_ciks, selected_variables, selected_indexes, start_year, end_year, use_yahoo):
    fig = go.Figure()

    if not selected_ciks and not selected_indexes:
        fig.update_layout(title="Vyberte alespoň jednu společnost nebo index.",
                          xaxis_title="Datum", yaxis_title="Hodnota")
        return fig

    if not selected_variables:
        selected_variables = ["Total assets"]
        print("[INFO] Default variable: Total assets")

    current_year = datetime.now().year
    start_year, end_year = min(start_year, end_year), max(start_year, end_year)
    if start_year > current_year or end_year > current_year:
        print(f"[ERROR] Year out of range. Current year: {current_year}")
        return fig

    # --- company filings (primary axis) ---
    for cik in (selected_ciks or []):
        company = companies.companies.get(cik)
        if not company:
            continue

        json_dir = f"xbrl_data_json/{company.ticker}"
        filings_loaded = []
        if os.path.exists(json_dir):
            for file in os.listdir(json_dir):
                if file.endswith(".json") and company.ticker in file:
                    filepath = os.path.join(json_dir, file)
                    data = _read_json(filepath)
                    if not data:
                        continue
                    dt = pd.to_datetime(data.get("date")).normalize()
                    if start_year <= dt.year <= end_year:
                        filings_loaded.append((dt, data))

        # Optionally ensure SEC fetch if too few filings per year
        for year in range(start_year, end_year + 1):
            # skip if we already have >=4 items that year
            if sum(1 for d, _ in filings_loaded if d.year == year) < 4:
                updated_company = info_picker_2.SecTools_export_important_data(
                    company, companies, year, mapping_variables=MAPPING_VARIABLE
                )
                if updated_company:
                    # load any new jsons added by the fetch
                    if os.path.exists(json_dir):
                        for file in os.listdir(json_dir):
                            if file.endswith(".json") and company.ticker in file:
                                filepath = os.path.join(json_dir, file)
                                data = _read_json(filepath)
                                if not data:
                                    continue
                                dt = pd.to_datetime(data.get("date")).normalize()
                                if start_year <= dt.year <= end_year and (dt, data) not in filings_loaded:
                                    filings_loaded.append((dt, data))

        for human_var in selected_variables:
            xs, ys, customdata = [], [], []

            is_ratio = human_var in RATIO_VARIABLES
            is_special_stock = (human_var == "Stock value")
            code = MAPPING_VARIABLE.get(human_var, human_var)

            for filing_dt, json_data in filings_loaded:
                if is_ratio:
                    # Read from computed
                    comp = (json_data.get("computed") or {})
                    value = comp.get(human_var)
                elif is_special_stock:
                    # Read saved Yahoo price directly from JSON
                    value = json_data.get("yf_value")
                else:
                    # GAAP variable: use helper to extract from base sheets
                    try:
                        value = info_picker_2.get_file_variable(code, json_data, year=filing_dt.year)
                    except Exception as e:
                        print(f"[ERROR] get_file_variable({code}) failed for {company.ticker}: {e}")
                        value = None

                y_num = None
                try:
                    y_num = float(value) if value is not None else None
                except Exception:
                    pass

                xs.append(filing_dt)
                ys.append(y_num)

                pretty_val = None
                if y_num is not None:
                    if is_ratio:
                        pretty_val = f"{y_num:.2f}"
                    elif is_special_stock:
                        pretty_val = f"{y_num:.2f} $"
                    else:
                        pretty_val = human_format(y_num)
                row = [pretty_val]
                customdata.append(row)

            # sort & filter out None
            combined = [(d, v, cd) for d, v, cd in zip(xs, ys, customdata) if v is not None]
            combined.sort(key=lambda x: x[0])
            if not combined:
                continue
            x_sorted, y_sorted, cd_sorted = zip(*combined)

            tooltip = (
                f"{company.title} - {human_var}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "Value: %{customdata[0]}<br>"
            )

            # Attach Yahoo price per filing date (skip duplication if we're already plotting Stock value)
            if use_yahoo and human_var != "Stock value":
                yf_map = info_picker_2.yf_get_stock_data(company.ticker, start_year, end_year) or {}
                yf_by_date = {pd.to_datetime(d).date(): v for d, v in yf_map.items() if v is not None}

                new_cd, has_any = [], False
                for d, row in zip(x_sorted, cd_sorted):
                    v = yf_by_date.get(d.date())
                    row = list(row)
                    row.append(v if v is not None else None)
                    if v is not None:
                        has_any = True
                    new_cd.append(row)
                cd_sorted = tuple(new_cd)
                if has_any:
                    tooltip += "Yahoo close: %{customdata[1]:.2f} $<br>"

            tooltip += "<extra></extra>"

            fig.add_trace(go.Scatter(
                x=list(x_sorted),
                y=[float(v) for v in y_sorted],
                mode='lines+markers',
                name=f"{company.title} - {human_var}",
                customdata=list(cd_sorted),
                hovertemplate=tooltip
            ))

    # --- Yahoo index overlay (secondary axis) ---
    if selected_indexes:
        for idx in selected_indexes:
            xy = info_picker_2.yf_download_series_xy(idx, start_year, end_year)
            if not xy:
                print(f"[WARNING] Index series empty for {idx}")
                continue
            x_vals, y_vals = xy
            fig.add_trace(go.Scatter(
                x=list(x_vals),
                y=[float(v) for v in y_vals],
                mode="lines",
                name=f"{idx} (Yahoo)",
                line=dict(dash="dash", width=3),
                yaxis="y2",
                hovertemplate="Index %{fullData.name}<br>Date: %{x|%Y-%m-%d}<br>Close: %{y:.2f} $<extra></extra>"
            ))

    fig.update_layout(
        title="Vývoj vybraných proměnných",
        xaxis_title="Datum filingů",
        yaxis_title="Hodnota (filings)",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="black",  # solid white background
            font_size=14,  # adjust to taste
            font_color="white"  # full color text
        ),
        yaxis=dict(type="log"),
        yaxis2=dict(
            title="Index (Yahoo)",
            overlaying="y",
            side="right",
            type="linear",
            showgrid=False
        ),
        legend=dict(x=1.10, y=1, xanchor="left", yanchor="top")
    )

    fig.update_xaxes(type="date", tickformat="%Y-%m-%d")
    return fig


def filter_summary_table(n_clicks, filter_value):
    if not filter_value or filter_value.strip() == "":
        return summary_df.to_dict("records")
    try:
        filtered_df = summary_df.query(filter_value)
        return filtered_df.to_dict("records")
    except Exception as e:
        print(f"[FILTER ERROR] {e}")
        return summary_df.to_dict("records")


# --------- Dropdown options incl. index shortcuts --------------------------
def build_company_dropdown_options():
    options = []
    options.append({"label": "— Indexes —", "value": "__SEP__IDX__", "disabled": True})
    for key, meta in PRESET_SOURCES.items():
        options.append({"label": meta["label"], "value": meta["shortcut"]})
    options.append({"label": "— All companies —", "value": "__SEP__ALL__", "disabled": True})
    for cik, comp in companies.companies.items():
        options.append({"label": f"{comp.title} [{comp.ticker}] ({cik})", "value": cik})
    return options

def build_variable_dropdown_options():
    """Group dropdown for the graph/table: base (human names), computed, specials."""
    options = []
    options.append({"label": "— Base variables —", "value": "__SEP__BASE__", "disabled": True})
    for key in MAPPING_VARIABLE.keys():
        options.append({"label": key, "value": key})  # value = human label

    options.append({"label": "— Computed variables —", "value": "__SEP__COM__", "disabled": True})
    for key in RATIO_VARIABLES:
        options.append({"label": key, "value": key})

    options.append({"label": "— Special variables —", "value": "__SEP__SPE__", "disabled": True})
    for key in SPECIAL_VARIABLES:
        options.append({"label": key, "value": key})
    return options


def expand_selected_values(values):
    """
    Expand index values (e.g., ^SPX, ^DJI) into constituent CIKs; keep direct CIKs as-is.
    IMPORTANT: If loader fails (e.g., HTTP 403), we return no expansion rather than raising.
    """
    if not values:
        return []
    expanded = set()
    for val in values:
        if isinstance(val, str) and val.startswith("^"):
            preset = next((m for m in PRESET_SOURCES.values() if m.get("shortcut") == val), None)
            if not preset:
                continue
            tickers = []
            try:
                tickers = preset["loader"]() or []
            except Exception as e:
                # Never break the whole flow if Wikipedia blocks scraping
                print(f"[ERROR] loader preset for {val}: {e} (continuing without expansion)")
                tickers = []
            for t in tickers:
                cik = TICKER_TO_CIK.get(str(t).upper())
                if cik:
                    expanded.add(cik)
        else:
            expanded.add(str(val))
    return list(expanded)


# ----------------------------- APP & CALLBACKS ------------------------------
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG]
)

# Initial table
summary_df = load_summary_table()
summary_columns = [{"name": col, "id": col} for col in summary_df.columns]
summary_data = summary_df.to_dict("records")

@app.callback(
    [Output('filing-graph', 'figure'),
     Output('error-message', 'children')],
    Input('draw-button', 'n_clicks'),
    [State('company-dropdown', 'value'),
     State('variable-dropdown', 'value'),
     State('year-start-input', 'value'),
     State('year-end-input', 'value'),
     State('filing-graph', 'figure'),
     State('yahoo-checkbox', 'value')]
)
def unified_callback(draw_clicks,
                     selected_values, selected_variables,
                     start_year, end_year, current_fig,
                      yahoo_state):
    triggered = callback_context.triggered[0]["prop_id"].split(".")[0]

    if triggered == "draw-button":
        values = selected_values or []
        if not isinstance(values, list):
            values = [values]
        selected_variables = selected_variables or []
        # drop group separators in the variables selector
        selected_variables = [v for v in selected_variables if v not in {"__SEP__BASE__", "__SEP__COM__", "__SEP__SPE__"}]

        if not (isinstance(start_year, int) and isinstance(end_year, int)):
            return no_update, "Zadejte platné roky (např. 2018 až 2022)."
        if start_year > end_year:
            return no_update, "Počáteční rok musí být menší nebo roven koncovému roku."

        selected_indexes = extract_selected_indexes(values)
        selected_ciks = expand_selected_values(values)

        if not selected_ciks and not selected_indexes:
            return no_update, "Vyberte alespoň jednu společnost nebo index."

        use_yahoo = bool(yahoo_state and ((isinstance(yahoo_state, list) and len(yahoo_state) > 0) or yahoo_state is True))

        fig = generate_graph(
            selected_ciks=selected_ciks,
            selected_variables=selected_variables,
            selected_indexes=selected_indexes,
            start_year=start_year,
            end_year=end_year,
            use_yahoo=use_yahoo
        )
        return fig, ""

    return no_update, no_update


# ----------------------------- APP LAYOUT ----------------------------------
app.layout = (
    html.Div([
        dcc.Loading(
            fullscreen=True,
            overlay_style={
                "visibility": "visible",
                "filter": "blur(2px)",
                "backgroundColor": "rgba(15,17,21,0.35)",
            },
            type="graph",
            children=[
                html.H1("Interaktivní vizualizace filingů", style={
                    "textAlign": "center",
                    "marginBottom": "30px"
                }),

                html.Div([
                    html.Div([
                        html.H6("Vyberte společnost / index:"),
                        dcc.Dropdown(
                            id='company-dropdown',
                            options=build_company_dropdown_options(),
                            multi=True,
                            placeholder="Vyberte jednu či více společností nebo index",
                            style={"color": "black"}
                        ),
                    ], style={'marginBottom': '20px'}),

                    html.Div([
                        html.H6("Vyberte proměnné (graf):"),
                        dcc.Dropdown(
                            id='variable-dropdown',
                            options=build_variable_dropdown_options(),
                            multi=True,
                            placeholder="Vyberte jednu nebo více proměnných",
                            style={"color": "black"}
                        ),
                    ], style={'marginBottom': '20px'}),

                    html.Div([
                        html.H6("Rozsah let:" ),
                        html.Div([
                            dcc.Input(id='year-start-input', type='number', step=1, value=YEAR_RANGE["start"],
                                      placeholder="Od roku", style={'marginRight': '20px', 'width': '100px'}),
                            dcc.Input(id='year-end-input', type='number', step=1, value=YEAR_RANGE["end"],
                                      placeholder="Do roku", style={'marginRight': '20px', 'width': '100px'}),
                            dcc.Checklist(
                                id='yahoo-checkbox',
                                options=[{'label': 'Zahrnout data z Yahoo', 'value': 'yahoo'}],
                                value=[],
                                inputStyle={"marginRight": "5px", "marginLeft": "20px"},
                                style={"color": "white"}
                            ),
                        ], style={'display': 'flex', 'alignItems': 'center'}),
                    ], style={'marginBottom': '20px'}),

                    html.Button("Aktualizuj období", id='draw-button', n_clicks=0, style={
                        "backgroundColor": "#2D8CFF",
                        "color": "white",
                        "border": "none",
                        "padding": "10px 20px",
                        "borderRadius": "5px",
                        "cursor": "pointer",
                        "marginBottom": "20px"
                    }),

                    html.Div(id='error-message', style={'color': 'red', 'marginBottom': '20px'})
                ], style={'maxWidth': '1200px', 'margin': '0 auto'}),

                html.Div([
                    dcc.Graph(
                        id='filing-graph',
                        style={"width": "100%"},
                        figure=go.Figure(layout={
                            "template": "plotly_dark",
                            "paper_bgcolor": "#000000",
                            "plot_bgcolor": "#000000"
                        })
                    ),
                    html.H3("Tabulka ukazatelů", style={"marginTop": "40px", "color": "white"}),

                    html.Div([
                        html.H6("Vyberte proměnné (tabulka):"),
                        dcc.Dropdown(
                            id='table-variables-dropdown',
                            options=build_table_variable_options(),
                            multi=True,
                            placeholder="Vyberte jednu či více proměnných pro tabulku",
                            style={"color": "black"}
                        ),
                    ], style={'marginBottom': '10px'}),

                    html.Button(
                        "Aktualizuj tabulku",
                        id='update-table-button',
                        n_clicks=0,
                        style={
                            "backgroundColor": "#2D8CFF",
                            "color": "white",
                            "border": "none",
                            "padding": "10px 20px",
                            "borderRadius": "5px",
                            "cursor": "pointer",
                            "marginBottom": "20px"
                        }
                    ),

                    dash_table.DataTable(
                        id='summary-table',
                        columns=summary_columns,
                        data=summary_data,
                        fixed_rows={'headers': True},
                        sort_action='native',
                        filter_action='native',
                        sort_mode="multi",
                        page_action='none',
                        style_table={'maxHeight': '500px', 'overflowY': 'auto', 'overflowX': 'auto',
                                     'border': '1px solid #444'},
                        style_cell={'textAlign': 'left', 'padding': '6px', 'backgroundColor': '#222',
                                    'color': '#e9ecef', 'border': '1px solid #444'},
                        style_header={'backgroundColor': '#2a2a2a', 'color': '#e9ecef', 'fontWeight': 'bold',
                                      'border': '1px solid #444'},
                    )
                ], style={'maxWidth': '1200px', 'margin': '40px auto'})
            ]
        ),
    ])
)


# ----------------------------- TABLE CALLBACK ------------------------------
@app.callback(
    [Output('summary-table', 'columns'),
     Output('summary-table', 'data')],
    Input('update-table-button', 'n_clicks'),
    State('table-variables-dropdown', 'value')
)
def update_summary_table(n_clicks, selected_vars):
    if not selected_vars:
        selected_vars = list(VARIABLES)
    else:
        selected_vars = [v for v in selected_vars if v not in {"__SEP__BASE__", "__SEP__COM__", "__SEP__SPE__"}]

    df = load_summary_table(selected_vars)

    base_cols = ["CIK", "Ticker", "Company", "Date"]
    columns = []
    for col in df.columns:
        if col in base_cols:
            columns.append({"name": col, "id": col})
        else:
            # Keep acronyms as-is; others title-case
            if col in RATIO_VARIABLES or col in SPECIAL_VARIABLES:
                columns.append({"name": col, "id": col})
            else:
                columns.append({"name": col.title(), "id": col})

    data = df.to_dict("records")
    return columns, data


# ----------------------------- RUN SERVER ----------------------------------
if __name__ == '__main__':
    if "WindowsApps" in sys.executable:
        raise RuntimeError("Debugger používá python.exe z WindowsApps – nepodporováno.")
    app.run(debug=True, use_reloader=False)
