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
        options=[{'label': v.title, 'value': k} for k, v in companies.companies.items()],
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
            xaxis_title="Čas (Rok-Čtvrtletí)",
            yaxis_title="Hodnota z filingů"
        )
        return fig

    for cik in selected_ciks:
        company = companies.companies.get(cik)
        if not company:
            continue

        x_values = []
        y_values = []
        for year, quarters in company.years.items():
            for quarter in quarters:
                x_values.append(f"{year}-Q{quarter.quarter}")
                y_values.append(quarter.filing.filing_date.year)  # Změnit podle požadované hodnoty

        fig.add_trace(go.Scatter(
            x=x_values,
            y=y_values,
            mode='lines+markers',
            name=company.title
        ))

    fig.update_layout(
        title="Vývoj hodnot filingů",
        xaxis_title="Čas (Rok-Čtvrtletí)",
        yaxis_title="Hodnota z filingů",
        xaxis=dict(tickangle=-45),
        template="plotly_dark"
    )
    return fig


if __name__ == '__main__':
    app.run(debug=True)