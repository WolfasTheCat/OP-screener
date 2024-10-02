# -*- coding: utf-8 -*-
"""
Created on Wed Mar 27 12:17:02 2024

@author: chodo
"""

# Import necessary libraries and modules
import yfinance as yf  # For downloading financial data
import plotly.graph_objects as plgo  # For visualizing data with Plotly
from datetime import datetime  # For handling dates and timestamps
import indicators  # Custom module for technical indicators (e.g., SMA, EMA, RSI)
import const  # Custom module for constants, such as file paths
import plotly.io as pio  # For handling Plotly I/O, like saving figures

# Setting default output format for Plotly figures to SVG
pio.kaleido.scope.default_format = "svg"


# The main function that orchestrates the entire visualization process
def main():
    # Dictionary to hold visualization components
    viz_objects = {"visualization": {}, "direct html": {}}

    # Download historical data for the S&P 500 Index (SPX) from Yahoo Finance, starting from 2018
    data = yf.download("^SPX", start="2018-01-01", end=datetime.now().strftime("%Y-%m-%d"))
    graph_title = "S&P 500 Index"

    # Create a technical analysis visualization with subplots and add it to the viz_objects dictionary
    ita_title = "Technical Analysis"
    hov_fig = hover_subplots(data, class_title=ita_title, graph_title=graph_title)
    viz_objects["visualization"][ita_title] = hov_fig

    # Generate HTML with multiple graphs on a webpage, using data from Yahoo Finance
    multiple_graphs_on_page(viz_objects, source="Yahoo Finance")


# Function to create interactive subplots with candlestick charts, moving averages, and volume
def hover_subplots(data, class_title, graph_title):
    # Define layout for the subplot figure
    layout = dict(
        hoversubplots="axis",
        title=class_title + " for " + graph_title,  # Title of the plot
        hovermode="x",  # Enables horizontal hover
        grid=dict(rows=3, columns=1),  # 3 rows and 1 column of subplots
        coloraxis=dict(colorscale='solar_r', showscale=False, colorbar_orientation="h")
        # Custom color scale for volume bars
    )

    # Create candlestick chart based on price data
    plots = [plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"],
                              name="Price", xaxis="x", yaxis="y")]

    # Add Simple Moving Averages (SMA) to the chart
    ma_range = (10, 20, 30, 50)
    for sma_n in ma_range:
        close_SMA = indicators.SMA(data["Close"], sma_n)  # Calculate SMA
        plots.append(
            plgo.Line(x=data.index[len(data["Close"]) - len(close_SMA):], y=close_SMA, name="SMA(" + str(sma_n) + ")",
                      xaxis="x", yaxis="y", visible=("legendonly" if sma_n != 20 else True)))

    # Add Exponential Moving Averages (EMA) to the chart
    for ema_n in ma_range:
        close_EMA = indicators.EMA(data["Close"], ema_n)  # Calculate EMA
        plots.append(
            plgo.Line(x=data.index[len(data["Close"]) - len(close_EMA):], y=close_EMA, name="EMA(" + str(ema_n) + ")",
                      xaxis="x", yaxis="y", visible="legendonly" if ema_n != 20 else True))

    # Add Relative Strength Index (RSI) plots to the chart
    for rsi_n in (9, 14, 26):
        close_RSI_n = indicators.RSI(data["Close"], rsi_n)  # Calculate RSI
        plots.append(plgo.Line(x=data.index[len(data["Close"]) - len(close_RSI_n):], y=close_RSI_n,
                               name="RSI(" + str(rsi_n) + ")", xaxis="x", yaxis="y2",
                               visible=("legendonly" if (rsi_n == 9) else True)))

    # Add a bar chart to display trading volume
    plots.append(plgo.Bar(x=data.index, y=data["Volume"], name="Volume", xaxis="x", yaxis="y3",
                          marker=dict(color=data["Volume"], coloraxis="coloraxis")))

    # Create a figure using the generated plots and layout
    fig = plgo.Figure(data=plots, layout=layout)

    # Update layout for figure elements
    fig.update_layout(
        title_text=class_title + " for " + graph_title,
        yaxis=dict(title="Price [USD]", overlaying="y", rangemode="tozero"),
        yaxis2=dict(title="RSI", overlaying="y2"),
        yaxis3=dict(title="Volume", overlaying="y3", rangemode="tozero"),
        xaxis=dict(overlaying="x", rangeslider_visible=False)
    )

    # Add custom buttons for range selection (e.g., 1 month, 6 months, etc.)
    fig.update_xaxes(
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(count=1, label="1y", step="year", stepmode="backward"),
                dict(step="all")
            ])
        )
    )

    # Customize colors for candlestick charts
    fig.data[0].increasing.line.color = "rgba(0,239,0, 0.5)"
    fig.data[0].increasing.fillcolor = "rgba(0,239,0, 0.5)"
    fig.data[0].decreasing.line.color = "rgba(127,127,0, 1)"
    fig.data[0].decreasing.fillcolor = "rgba(127,127,0, 1)"

    # Color scheme for other plots (moving averages, RSI, etc.)
    clrs = ['#000000', '#D8D844', '#909000', '#A4A400', '#707000', '#505000', '#BFBF00', '#343400']
    for i in range(1, len(plots) - 1, 1):
        fig['data'][i]['line']['color'] = clrs[i - 1]

    # Configuration for exporting the figure as an SVG image
    config = {
        'toImageButtonOptions': {
            'format': 'svg',  # Set the default format to SVG
            'filename': 'custom_image',  # Default filename
            'height': 600,  # Default height
            'width': 800,  # Default width
            'scale': 1  # Default scale
        }
    }

    # Convert the figure to HTML format
    html_str = pio.to_html(fig, full_html=False, include_plotlyjs='cdn', config=config)

    return html_str


# Function to create and save multiple graphs on a webpage
def multiple_graphs_on_page(viz_objects, file=const.RESULTING_FILE, source="Yahoo Finance"):
    # Open the resulting file for writing HTML content
    with open(file, "w", encoding="utf8") as fig:
        fig.write("<html> <head> <title>Screener</title></head> ")

        # Write custom CSS styles for the webpage
        with open("./style.css", "r") as f:
            css = f.readlines()
            fig.writelines(css)

        fig.write("<body>\n")

        # Add tabs for each visualization
        graphs = viz_objects["visualization"]
        fig.write(""" <div class="tab"> """)

        def_tab = True
        for k in graphs:
            fig.write("""
                <button class="tablinks" onclick="openTab(event, ' """ + k + """ ')" """ + (
                """id="defaultOpen" """ if def_tab else "") + """>""" + k + """</button>
            """)
            def_tab = False

        fig.write("</div>")

        # Add graph content to each tab
        for k in graphs:
            fig.write("""<div id=' """ + k + """ ' class="tabcontent">""")
            fig.write(graphs[k])
            fig.write("</div>")

        # Add other direct HTML content
        for k in viz_objects["direct html"]:
            fig.write(viz_objects["direct html"][k])

        # Footer information
        fig.write(
            "<div>Volume supportive color-scale: dark color indicates high values, light color indicates low values.</div>")
        fig.write(
            "<div><small>" + datetime.now().strftime("%d. %m. %Y %H:%M:%S") + "</small> Source: " + source + "</div>")

        # Include custom JavaScript
        with open("./script.js", "r") as f:
            js = f.readlines()
            fig.writelines(js)

        fig.write("</body> </html>\n")


# Main execution
if __name__ == "__main__":
    main()
