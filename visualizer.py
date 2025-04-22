import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import info_picker_2  # Import funkcí pro zpracování filing dat

# Inicializace Dash aplikace
app = dash.Dash(__name__)

# Získání seznamu společností
companies = info_picker_2.CompanyData()
companies.load_saved_companies()

app.layout = html.Div([
    html.H1("Interaktivní vizualizace filingů"),
    dcc.Dropdown(
        id='company-dropdown',
        options=[{'label': v.title + " ("+ k +")", 'value': k} for k, v in companies.companies.items()],
        multi=True,
        placeholder="Vyberte jednu či více společností"
    ),
    dcc.Graph(id='filing-graph')
])


@app.callback(
    Output('filing-graph', 'figure'),
    [Input('company-dropdown', 'value')]
)
def update_graph(selected_ciks):
    fig = go.Figure()
    if not selected_ciks:
        fig.update_layout(
            title="Vyberte alespoň jednu společnost pro zobrazení dat.",
            xaxis_title="Datum filingů",
            yaxis_title="Total Assets"
        )
        return fig

    for cik in selected_ciks:
        company = companies.companies.get(cik)
        if not company:
            continue

        # Pokud chybí data, stáhneme je
        if not company.years or all(len(q) == 0 for q in company.years.values()):
            updated_company = info_picker_2.SecTools_export_important_data(company, companies)
            if updated_company:
                companies.companies[cik] = updated_company
                company = updated_company

        x_values = []
        y_values = []

        for year, filings in company.years.items():
            for filing in filings:
                if filing.date and filing.financials:
                    x_values.append(filing.date)
                    temp = info_picker_2.get_sheet_variable("Total assets", filing.financials.balance_sheet)
                    if temp is not None and len(temp) > 0:
                        y_values.append(int(temp))

        if not x_values or not y_values:
            continue

        fig.add_trace(go.Scatter(
            x=x_values,
            y=y_values,
            mode='lines+markers',
            name=company.title
        ))

    fig.update_layout(
        title="Vývoj Total Assets v čase",
        xaxis_title="Datum filingů",
        yaxis_title="Total Assets",
        xaxis=dict(tickangle=-45),
        yaxis=dict(autorange=True),
        template="plotly_dark"
    )
    return fig


if __name__ == '__main__':
    app.run(debug=True)