import os
import json
from datetime import datetime

import dash
import pandas as pd
from dash import dcc, html, dash_table, callback_context, no_update
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import info_picker_2


# ----------------------------- CONSTANTS -----------------------------------
VARIABLE_SHEETS = {
    "total assets": "balance_sheet",
    "total liabilities": "balance_sheet",
    "cash": "balance_sheet",
    "Shares Outstanding": "income"
}
VARIABLES = list(VARIABLE_SHEETS.keys())
YEAR_RANGE = {"start": 2018, "end": datetime.now().year - 3}


# ----------------------------- LOAD COMPANY DATA ---------------------------
companies = info_picker_2.CompanyData()
companies.load_saved_companies()


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
        return df  # nebo return pd.DataFrame(columns=["CIK", "Ticker", "Company", "Date", ...])

    print("Sloupce v df:", df.columns)  # ladění

    df.sort_values(["Company", "Date"], inplace=True)
    return df


def generate_graph(selected_ciks, selected_variables, start_year, end_year):
    fig = go.Figure()
    if not selected_ciks:
        fig.update_layout(title="Vyberte alespoň jednu společnost.", xaxis_title="Datum", yaxis_title="Hodnota")
        return fig

    if not selected_variables:
        selected_variables = ["total assets"]
        print("[INFO] Výchozí proměnná: total assets")

    current_year = datetime.now().year
    start_year, end_year = min(start_year, end_year), max(start_year, end_year)
    if start_year > current_year or end_year > current_year:
        print(f"[ERROR] Rok mimo rozsah. Aktuální rok: {current_year}")
        return fig

    for cik in selected_ciks:
        company = companies.companies.get(cik)
        if not company:
            continue
        print(f"[DEBUG] Zpracovávám: {company.ticker} ({company.title})")
        loaded_years = set()
        json_dir = f"xbrl_data_json/{company.ticker}"

        if os.path.exists(json_dir):
            for file in os.listdir(json_dir):
                if file.endswith(".json") and company.ticker in file:
                    filepath = os.path.join(json_dir, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                        date = pd.to_datetime(json_data["date"])
                        year = date.year
                        if not (start_year <= year <= end_year):
                            continue

                        def make_sheet(data_dict):
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

        for year in range(start_year, end_year + 1):
            if year not in loaded_years:
                print(f"[DEBUG] Stahuji rok {year}...")
                updated_company = info_picker_2.SecTools_export_important_data(company, companies, year)
                if updated_company:
                    company.years.update(updated_company.years)

        for variable in selected_variables:
            x_values, y_values = [], []
            for year, filings in company.years.items():
                if not (start_year <= year <= end_year):
                    continue
                for filing in filings:
                    if not (filing.date and filing.financials):
                        continue
                    value = None
                    for sheet_name in ["balance_sheet", "income", "cashflow"]:
                        sheet = getattr(filing.financials, sheet_name)
                        value = info_picker_2.get_file_variable(variable, sheet, year)
                        if value is not None:
                            break
                    try:
                        y = float(value) if value is not None else None
                    except ValueError:
                        y = None
                    x_values.append(pd.to_datetime(filing.date))
                    y_values.append(y)

            combined = [(d, v) for d, v in zip(x_values, y_values) if v is not None]
            combined.sort(key=lambda x: x[0])
            if combined:
                x_sorted, y_sorted = zip(*combined)
                fig.add_trace(go.Scatter(
                    x=x_sorted, y=y_sorted,
                    mode='lines+markers',
                    name=f"{company.title} - {variable}"
                ))

    fig.update_layout(
        title="Vývoj vybraných proměnných",
        xaxis_title="Datum filingů",
        yaxis_title="Hodnota",
        template="plotly_dark"
    )
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
     State('filing-graph', 'figure')],
)
def unified_callback(draw_clicks,
                     selected_ciks, selected_variables,
                     start_year, end_year, current_fig
                     ):
    triggered = callback_context.triggered[0]["prop_id"].split(".")[0]

    if triggered == "draw-button":
        selected_ciks = [selected_ciks] if isinstance(selected_ciks, (str, int)) else (selected_ciks or [])
        selected_variables = selected_variables or []

        if not (isinstance(start_year, int) and isinstance(end_year, int)):
            return no_update, "Zadejte platné roky (např. 2018 až 2022).", no_update

        if start_year > end_year:
            return no_update, "Počáteční rok musí být menší nebo roven koncovému roku.", no_update

        if not selected_ciks:
            return no_update, "Vyberte alespoň jednu společnost.", no_update

        fig = generate_graph(selected_ciks, selected_variables, start_year, end_year)
        return fig, "", no_update

    return no_update, no_update, no_update


# ----------------------------- APP LAYOUT ----------------------------------

app.layout = html.Div([
    html.H1("Interaktivní vizualizace filingů", style={
        "textAlign": "center",
        "color": "#FFFFFF",
        "marginBottom": "30px"
    }),

    html.Div([
        html.Div([
            html.Label("Vyberte společnost:", style={"fontWeight": "bold", "color": "white"}),
            dcc.Dropdown(
                id='company-dropdown',
                options=[{'label': f"{v.title} ({k})", 'value': k} for k, v in companies.companies.items()],
                multi=True,
                placeholder="Vyberte jednu či více společností"
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
                          placeholder="Do roku", style={'width': '100px'})
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
], style={'backgroundColor': '#1a1a1a', 'minHeight': '100vh', 'margin': '0', 'padding': '0'})



# ----------------------------- RUN SERVER ----------------------------------

if __name__ == '__main__':
    app.run(debug=True)
