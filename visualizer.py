import os
import json
import sys
from datetime import datetime

import dash
import pandas as pd
from dash import dcc, html, dash_table, callback_context, no_update
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go

import info_picker_2
from helper import human_format, get_selected_indexes, extract_selected_indexes

# ----------------------------- CONSTANTS -----------------------------------
VARIABLE_SHEETS = {
    "total assets": "balance_sheet",
    "total liabilities": "balance_sheet",
    "cash": "balance_sheet",
    "Shares Outstanding": "income"
}
VARIABLES = list(VARIABLE_SHEETS.keys())
YEAR_RANGE = {"start": 2018, "end": datetime.now().year - 7}

# Presets of indexes
PRESET_SOURCES = {
    "sp500": {
        "label": "S&P 500",
        "loader": info_picker_2.download_SP500_tickers,
        "shortcut": "^SPX"
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

# TICKER -> CIK
TICKER_TO_CIK = {v.ticker.upper(): k for k, v in companies.companies.items()}


# ----------------------------- FUNCTIONS -----------------------------------

def load_summary_table():
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
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                report_date = pd.to_datetime(data.get("date", None))
                if not report_date:
                    continue

                row = {"CIK": cik, "Ticker": ticker, "Company": name, "Date": report_date.strftime("%Y-%m-%d")}
                for var in VARIABLES:
                    sheet_data = data.get(VARIABLE_SHEETS[var], {})
                    df = pd.DataFrame.from_dict(sheet_data)
                    value = None
                    if not df.empty:
                        for alias in info_picker_2.VARIABLE_ALIASES.get(var.lower(), [var.lower()]):
                            for row_label in df.index:
                                if row_label.strip().lower() == alias:
                                    value = df.loc[row_label].dropna().iloc[0]
                                    break
                            if value is not None:
                                break
                        if value is None:
                            for alias in info_picker_2.VARIABLE_ALIASES.get(var.lower(), [var.lower()]):
                                for row_label in df.index:
                                    if alias in row_label.strip().lower():
                                        value = df.loc[row_label].dropna().iloc[0]
                                        break
                                if value is not None:
                                    break
                    try:
                        row[var] = int(value)
                    except (ValueError, TypeError):
                        row[var] = value
                records.append(row)
            except Exception as e:
                print(f"[ERROR] {filepath} – {e}")

    columns = ["CIK", "Ticker", "Company", "Date"] + VARIABLES
    df = pd.DataFrame(records, columns=columns)

    if df.empty:
        print("[WARNING] Žádné záznamy nebyly načteny.")
        return df

    df.sort_values(["Company", "Date"], inplace=True)
    return df


def generate_graph(selected_ciks, selected_variables, selected_indexes, start_year, end_year, use_yahoo):
    fig = go.Figure()

    if not selected_ciks and not selected_indexes:
        fig.update_layout(title="Vyberte alespoň jednu společnost nebo index.",
                          xaxis_title="Datum", yaxis_title="Hodnota")
        return fig

    if not selected_variables:
        selected_variables = ["total assets"]
        print("[INFO] Výchozí proměnná: total assets")

    current_year = datetime.now().year
    start_year, end_year = min(start_year, end_year), max(start_year, end_year)
    if start_year > current_year or end_year > current_year:
        print(f"[ERROR] Rok mimo rozsah. Aktuální rok: {current_year}")
        return fig

    # ---------------- Filing traces (companies) ----------------
    for cik in (selected_ciks or []):
        company = companies.companies.get(cik)
        if not company:
            continue
        print(f"[DEBUG] Zpracovávám: {company.ticker} ({company.title})")

        loaded_years = set()
        json_dir = f"xbrl_data_json/{company.ticker}"

        # Load cached JSONs if present
        if os.path.exists(json_dir):
            for file in os.listdir(json_dir):
                if file.endswith(".json") and company.ticker in file:
                    filepath = os.path.join(json_dir, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                        date = pd.to_datetime(json_data["date"]).normalize()  # <<< normalize
                        year = date.year
                        if not (start_year <= year <= end_year):
                            continue

                        def make_sheet(data_dict):
                            # Always return an object with .data == DataFrame
                            return type("Sheet", (object,), {
                                "data": pd.DataFrame.from_dict(data_dict)
                            })()

                        financials = type("Financials", (object,), {
                            "balance_sheet": make_sheet(json_data.get("balance_sheet", {})),
                            "income": make_sheet(json_data.get("income", {})),
                            "cashflow": make_sheet(json_data.get("cashflow", {}))
                        })()

                        if year not in company.years:
                            company.years[year] = []
                        if not any(f.date == date for f in company.years[year]):
                            company.years[year].append(
                                info_picker_2.CompanyFinancials(date, financials, location=filepath)
                            )
                        loaded_years.add(year)
                    except Exception as e:
                        print(f"[ERROR] Chyba při načítání {file}: {e}")

        # Fetch missing years from SEC if needed
        for year in range(start_year, end_year + 1):
            if year not in loaded_years:
                print(f"[DEBUG] Stahuji rok {year}...")
                updated_company = info_picker_2.SecTools_export_important_data(company, companies, year)
                if updated_company:
                    company.years.update(updated_company.years)

        # Build traces per variable
        for variable in selected_variables:
            x_values, y_values = [], []
            for year, filings in company.years.items():
                if not (start_year <= year <= end_year):
                    continue
                for filing in filings:
                    if not (filing.date and filing.financials):
                        continue

                    # ensure normalized, tz-naive timestamp for X
                    filing_dt = pd.to_datetime(filing.date).normalize()  # <<< normalize
                    financials_obj = filing.financials
                    value = None

                    for sheet_name in ["balance_sheet", "income", "cashflow"]:
                        try:
                            if hasattr(financials_obj, sheet_name):
                                sheet = getattr(financials_obj, sheet_name)  # wrapper with .data
                            elif hasattr(financials_obj, f"get_{sheet_name}"):
                                raw_df = getattr(financials_obj, f"get_{sheet_name}")()
                                sheet = type("Sheet", (object,), {"data": pd.DataFrame(raw_df)})()
                            else:
                                continue

                            value = info_picker_2.get_file_variable(variable, sheet, year)
                            if value is not None:
                                break
                        except Exception as e:
                            print(f"[ERROR] Chyba při čtení {sheet_name} pro {company.ticker}: {e}")
                            continue

                    try:
                        y_num = float(value) if value is not None else None
                    except ValueError:
                        y_num = None

                    x_values.append(filing_dt)
                    y_values.append(y_num)

            combined = [(d, v) for d, v in zip(x_values, y_values) if v is not None]
            combined.sort(key=lambda x: x[0])
            if combined:
                x_sorted, y_sorted = zip(*combined)

                # Tooltip with human_format + optional Yahoo price
                custom_template = (
                    f"{company.title} - {variable}<br>"
                    "Datum: %{x|%Y-%m-%d}<br>"
                    "Hodnota: %{customdata[0]} $<br>"
                )
                customdata = [[human_format(v)] for v in y_sorted]

                if use_yahoo:
                    yahoo_map = info_picker_2.yf_get_stock_data(company.ticker, start_year, end_year) or {}
                    yahoo_dict = {pd.to_datetime(d).date(): v for d, v in yahoo_map.items() if v is not None}
                    yahoo_vals = [yahoo_dict.get(d.date(), None) for d in x_sorted]
                    if any(v is not None for v in yahoo_vals):
                        for row, yf in zip(customdata, yahoo_vals):
                            row.append(None if yf is None else float(yf))
                        custom_template += "Yahoo akcie: %{customdata[1]:.2f} $<br>"

                custom_template += "<extra></extra>"

                fig.add_trace(go.Scatter(
                    x=list(x_sorted),
                    y=[float(v) for v in y_sorted],
                    mode='lines+markers',
                    name=f"{company.title} - {variable}",
                    customdata=customdata,
                    hovertemplate=custom_template
                ))

    # --- Yahoo index traces on secondary axis ---
    if selected_indexes:
        for selected_index in selected_indexes:
            x_vals, y_vals = info_picker_2.yf_download_series_xy(selected_index, start_year, end_year)
            if not x_vals and not y_vals:
                print(f"[WARNING] Index series empty for {selected_index}")
                continue

            fig.add_trace(go.Scatter(
                x=list(x_vals),
                y=[float(v) for v in y_vals],
                mode="lines",
                name=f"{selected_index} (Yahoo)",
                line=dict(dash="dash", width=3),
                yaxis="y2",
                hovertemplate="Index %{fullData.name}<br>Datum: %{x|%Y-%m-%d}<br>Close: %{y:.2f} $<extra></extra>"
            ))

    # layout must define y2:
    fig.update_layout(
        yaxis=dict(type="log"),
        yaxis2=dict(
            title="Index (Yahoo)",
            overlaying="y",
            side="right",
            type="linear",
            showgrid=False
        ),
    )
    # unified X format:
    fig.update_xaxes(type="date", tickformat="%Y-%m-%d")

    # Final layout: unified X format, left (log) for filings, right (linear) for indices
    fig.update_layout(
        title="Vývoj vybraných proměnných",
        xaxis_title="Datum filingů",
        yaxis_title="Hodnota (filings)",
        template="plotly_dark",
        yaxis=dict(type="log"),
        yaxis2=dict(
            title="Index (Yahoo)",
            overlaying="y",
            side="right",
            type="linear",
            showgrid=False
        ),
        hovermode="x unified",
        legend=dict(
            x=1.10,  # push legend a bit right from the plot area
            y=1,
            xanchor="left",  # anchor left edge of legend box at that x
            yanchor="top",
            bgcolor="rgba(0,0,0,0)"  # transparent background (optional)
        )
    )

    # Force the same visible tick format on X for both traces
    fig.update_xaxes(type="date", tickformat="%Y-%m-%d")  # <<< jednotný formát osy X

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


# --------- Helpers: options with indexes -------------

def build_company_dropdown_options():
    options = []
    options.append({"label": "— Indexes —", "value": "__SEP__IDX__", "disabled": True})

    # preset values should be Yahoo shortcuts (e.g., ^SPX, ^DJI)
    for key, meta in PRESET_SOURCES.items():
        options.append({
            "label": meta["label"],
            "value": meta["shortcut"]   # <<<<<< was "__IDX__{key}"
        })

    options.append({"label": "— All companies —", "value": "__SEP__ALL__", "disabled": True})

    for cik, comp in companies.companies.items():
        options.append({
            "label": f"{comp.title} [{comp.ticker}] ({cik})",
            "value": cik
        })
    return options

def expand_selected_values(values):
    """
    Expand index values (e.g., ^SPX, ^DJI) into constituent CIKs;
    keep directly-selected CIKs as-is.
    """
    if not values:
        return []
    expanded = set()
    for val in values:
        if isinstance(val, str) and val.startswith("^"):
            # find matching preset by shortcut
            preset = next((m for m in PRESET_SOURCES.values() if m.get("shortcut") == val), None)
            if not preset:
                continue
            try:
                tickers = preset["loader"]() or []
            except Exception as e:
                print(f"[ERROR] loader preset for {val}: {e}")
                tickers = []
            for t in tickers:
                cik = TICKER_TO_CIK.get(str(t).upper())
                if cik:
                    expanded.add(cik)
        else:
            expanded.add(str(val))
    return list(expanded)




# ----------------------------- APP & CALLBACK ------------------------------

app = dash.Dash(__name__)

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Filing Visualizer</title>
        {%favicon%}
        {%css%}
        <style>
            body, html {
                margin: 0;
                padding: 0;
                background-color: #1a1a1a;
                font-family: sans-serif;
                overflow-x: hidden;
            }
            .custom-loader.dash-loading > .dash-loading-overlay{
                position: fixed;
                inset: 0;
                background: rgba(15,17,21,0.45) !important;
                backdrop-filter: blur(2px);
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .custom-loader .dash-spinner{
                width: 64px;
                height: 64px;
                border-width: 6px;
                filter: drop-shadow(0 0 10px rgba(45,140,255,0.55));
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

summary_df = load_summary_table()
summary_columns = [{"name": col, "id": col} for col in summary_df.columns]
summary_data = summary_df.to_dict("records")

@app.callback(
    [Output('filing-graph', 'figure'),
     Output('error-message', 'children'),
     Output('summary-table', 'data')],
    Input('draw-button', 'n_clicks'),
    [State('company-dropdown', 'value'),
     State('variable-dropdown', 'value'),
     State('year-start-input', 'value'),
     State('year-end-input', 'value'),
     State('filing-graph', 'figure'),
     State('finnhub-checkbox', 'value'),
     State('yahoo-checkbox', 'value')]
)
def unified_callback(draw_clicks,
                     selected_values, selected_variables,
                     start_year, end_year, current_fig,
                     finnhub_value, yahoo_state):
    triggered = callback_context.triggered[0]["prop_id"].split(".")[0]

    if triggered == "draw-button":
        # Normalize inputs
        values = selected_values or []
        if not isinstance(values, list):
            values = [values]
        selected_variables = selected_variables or []

        # Basic year validation
        if not (isinstance(start_year, int) and isinstance(end_year, int)):
            return no_update, "Zadejte platné roky (např. 2018 až 2022).", no_update
        if start_year > end_year:
            return no_update, "Počáteční rok musí být menší nebo roven koncovému roku.", no_update

        # Extract indexes (^GSPC, ^DJI, …) and expand to CIKs for filings
        selected_indexes = extract_selected_indexes(values)

        # IMPORTANT: pass the FULL selection to the expander so that
        # - CIKs stay as-is
        # - ^INDEX expands to constituent CIKs
        selected_ciks = expand_selected_values(values)

        if not selected_ciks and not selected_indexes:
            return no_update, "Vyberte alespoň jednu společnost nebo index.", no_update

        use_yahoo = bool(yahoo_state and ((isinstance(yahoo_state, list) and len(yahoo_state) > 0) or yahoo_state is True))

        fig = generate_graph(
            selected_ciks=selected_ciks,
            selected_variables=selected_variables,
            selected_indexes=selected_indexes,  # <<<<<< pass caret tickers here
            start_year=start_year,
            end_year=end_year,
            use_yahoo=use_yahoo
        )
        return fig, "", no_update

    return no_update, no_update, no_update



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
                    "color": "#FFFFFF",
                    "marginBottom": "30px"
                }),

                html.Div([
                    html.Div([
                        html.Label("Vyberte společnost / index:", style={"fontWeight": "bold", "color": "white"}),
                        dcc.Dropdown(
                            id='company-dropdown',
                            options=build_company_dropdown_options(),  # <-- flat options s indexy nahoře
                            multi=True,
                            placeholder="Vyberte jednu či více společností nebo index"
                        ),
                    ], style={'marginBottom': '20px'}),

                    html.Div([
                        html.Label("Vyberte proměnné:", style={"fontWeight": "bold", "color": "white"}),
                        dcc.Dropdown(
                            id='variable-dropdown',
                            options=[{'label': k.title(), 'value': k} for k in info_picker_2.VARIABLE_ALIASES.keys()],
                            multi=True,
                            placeholder="Vyberte jednu nebo více proměnných"
                        ),
                    ], style={'marginBottom': '20px'}),

                    html.Div([
                        html.Label("Rozsah let:", style={"fontWeight": "bold", "color": "white"}),
                        html.Div([
                            dcc.Input(id='year-start-input', type='number', step=1, value=YEAR_RANGE["start"],
                                      placeholder="Od roku", style={'marginRight': '20px', 'width': '100px'}),
                            dcc.Input(id='year-end-input', type='number', step=1, value=YEAR_RANGE["end"],
                                      placeholder="Do roku", style={'marginRight': '20px', 'width': '100px'}),
                            dcc.Checklist(
                                id='finnhub-checkbox',
                                options=[{'label': 'Zahrnout data z Finnhub', 'value': 'finnhub'}],
                                value=[],
                                inputStyle={"marginRight": "5px"},
                                style={"color": "white"}
                            ),
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
                    html.H3("Tabulka ukazatelů", style={"marginTop": "40px", "color": "#FFFFFF"}),

                    dash_table.DataTable(
                        id='summary-table',
                        columns=summary_columns,
                        data=summary_data,
                        fixed_rows={'headers': True},
                        sort_action='native',
                        filter_action='native',
                        sort_mode="multi",
                        page_action='none',
                        style_table={
                            'maxHeight': '500px',
                            'overflowY': 'auto',
                            'overflowX': 'auto',
                            'border': '1px solid #444'
                        },
                        style_cell={'textAlign': 'left', 'padding': '5px'},
                        style_header={'backgroundColor': 'rgb(30, 30, 30)', 'color': 'white'},
                        style_data={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white'},
                    )
                ], style={'maxWidth': '1200px', 'margin': '40px auto'})
            ]
        ),
    ])
)


# ----------------------------- RUN SERVER ----------------------------------

if __name__ == '__main__':
    if "WindowsApps" in sys.executable:
        raise RuntimeError("Debugger používá python.exe z WindowsApps – nepodporováno.")
    app.run(debug=True, use_reloader=False)

