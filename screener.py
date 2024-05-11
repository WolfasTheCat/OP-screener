# -*- coding: utf-8 -*-
"""
Created on Wed Mar 27 12:17:02 2024
                                                                                                                                                                                                                                                                
@author: chodo
"""

import yfinance as yf

# import plotly.express as plx
import plotly.offline as plo

import plotly.graph_objects as plgo
import data_loader
import plotly.subplots as plsub

from datetime import datetime

import indicators
import const

def main():
    viz_objects = {"visualization":{},"direct html":[]}
    
    
    # As JSON:
    #edgar_reports = load_edgar(path="../edgar-crawler-main/datasets/EXTRACTED_FILINGS/")
    #for k in edgar_reports:
    #    text_area = "<div>"+edgar_reports[k]["item_6"][:300]+"</div>"
    #    viz_objects["direct html"].append(text_area)
    
    # As
    """ EDGAR in pure HTML
    edgar_reports = load_edgar(path="../edgar-crawler-main/datasets/RAW_FILINGS/", file_format=data_loader.Convertions.HTML)
    edgar_reports.keys()
    kys = edgar_reports['C:\\Users\\chodo\\Documents\\Studies\\Projects\\Masters\\KIV-VI\\semestrálka\\edgar-crawler-main\\datasets\\RAW_FILINGS\\320193_10K_2015_0001193125-15-356351.htm']
    text_area = "<div>"+kys+"</div>"
    viz_objects["direct html"].append(text_area)
    """
    data = yf.download("^SPX", start="2020-01-01", end=datetime.now().strftime("%Y-%m-%d"))
    #viz_objects["visualization"].append(plx.bar(x=data.index, y=data["Close"]))
    
    graph_title = "S&P 500 Index"
    #, "yaxis":"Price [USD]", "xaxis":"Time"
    
    
    #original#candle_graph = plgo.Figure( plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"]), layout=graph_layout )
    

    price_title = "Price Developement"
    price_graph = price_graphs(data, title=price_title+" of "+graph_title)
    
    
    #histogram_sub   = plgo.Histogram(   x=data.index, y=data["Volume"], name="Histogram", visible="legendonly")
    
    
    viz_objects["visualization"][price_title] = price_graph
    ita_title = "Indicators of Technical Analysis"
    viz_objects["visualization"][ita_title] = x_shared_subplots(data, class_title=ita_title, graph_title=graph_title)
    multiple_graphs_on_page(viz_objects)
    
    
def x_shared_subplots(data, class_title, graph_title):
    fig = plsub.make_subplots(rows=3, cols=1,
                        shared_xaxes=True,# = "columns", "rows", "all"
                        vertical_spacing=0.01)
    fig.update_layout(title_text=class_title+" for "+graph_title)
    fig.update_legends(title_text=class_title)
    
    append_price_traces(data, fig, row=1, col=1)
    
    append_rsi_traces(data, fig, row=2, col=1)
    
    append_volume_traces(data, fig, row=3, col=1)
    fig.update_xaxes(title_text="Time", row=3, col=1)
    #fig.update_traces(marker=dict(color='#917A48'), row=3, col=1)
    #fig.update_layout(coloraxis=dict(colorscale='Bluered'), showlegend=False)# ->Bluered_r for reversed scale
    
    #fig.update_xaxes(matches='x')# share axes
    fig.update_layout(hovermode="x unified", coloraxis=dict(colorscale='solar_r', showscale=False, colorbar_orientation="h"))# show vertical line hover
    #fig.update_xaxes(rangeslider_visible=True, row=3, col=1)# time-wheel
    #, hovertemplate="%{y}%{_xother}"

    fig.update_xaxes(# time buttons
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1m", step="month", stepmode="backward"),
            dict(count=6, label="6m", step="month", stepmode="backward"),
            #dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1y", step="year", stepmode="backward"),
            dict(step="all")
        ])
    )
    , row=1, col=1)
    
    fig.update_xaxes(# time range
        rangeslider_visible=True,
        
        rangeslider_thickness=0.15# default 0.15
        , rangeslider_bordercolor="black"
        , row=3, col=1)
    return fig

def append_price_traces(data, fig, row, col):
    fig.append_trace(#add_trace
                     plgo.Line(x=data.index, y= data["Close"], name="Close")
                , row=row, col=col)
    for sma_n in (10, 20, 30, 50):
        close_SMA = indicators.SMA(data["Close"], sma_n)
        fig.append_trace(
            plgo.Line(x=data.index[len(data["Close"])-len(close_SMA):], y= close_SMA, name="SMA("+str(sma_n)+")", visible="legendonly" if sma_n!=20 else True)
        , row=row, col=col)
    for ema_n in (10, 20, 30, 50):
        close_EMA = indicators.EMA(data["Close"], ema_n)
        fig.append_trace(
            plgo.Line(x=data.index[len(data["Close"])-len(close_EMA):], y= close_EMA, name="EMA("+str(ema_n)+")", visible="legendonly" if ema_n!=20 else True)
        , row=row, col=col)
    fig.update_yaxes(title_text="Price [USD]", row=row, col=col)#, hovertemplate="%{y}%{_xother}"

def append_rsi_traces(data, fig, row, col):
    for rsi_n in (9, 14, 26):
        close_RSI_n = indicators.RSI(data["Close"], rsi_n)
        fig.append_trace(
            plgo.Line(x=data.index[len(data["Close"])-len(close_RSI_n):], y= close_RSI_n, name="RSI("+str(rsi_n)+")", visible="legendonly" if rsi_n!=14 else True)
    , row=row, col=col)
    fig.update_yaxes(title_text="Relative Strength Index", row=row, col=col)

def append_volume_traces(data, fig, row, col):
    fig.append_trace(
        plgo.Bar(x=data.index, y=data["Volume"], name="Volume", marker=dict(color=data["Volume"], coloraxis="coloraxis"))
    , row=row, col=col)
    fig.update_yaxes(title_text="Volume of Shares Traded", row=row, col=col)

def price_graphs(data, title):
    #price_subs = moving_averages_subgraphs(data)
    
    price_candle_sub = plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"], name="Candlestick")
    #price_subs.append(price_candle_sub)
    
    price_graph = plgo.Figure(data=price_candle_sub, layout={"title":{"text":title}, "xaxis_title":{"text":"Time"}, "yaxis_title":{"text":"Price USD"}} )
    price_graph.update_yaxes(fixedrange=False)# fixing the y-range of the graph <3
    return price_graph



def multiple_graphs_on_page(viz_objects, file=const.RESULTING_FILE):
    with open(file,"w",encoding="utf8") as fig:# <3 \u2665
        fig.write("<html> <head> <title>Screener</title></head> ")
        with open("./style.css", "r") as f:
            css = f.readlines()
            fig.writelines(css)
                  
        fig.write("<body>\n")
        include_js = True
        
        graphs = viz_objects["visualization"]
        fig.write(""" <div class="tab"> """)
        
        def_tab = True
        for k in graphs:
            fig.write("""
                          <button class="tablinks" onclick="openTab(event, ' """+k+""" ')" """+("""id="defaultOpen" """if def_tab else "" )+""">"""+k+"""</button>
                    """)
            def_tab = False
        fig.write("</div>")
        for k in graphs:
            fig.write("""<div id=' """+k+""" ' class="tabcontent">""")
            
            fig.write(plo.plot(graphs[k], include_plotlyjs=include_js,output_type="div"))
            
            fig.write("</div>")
            include_js = False
        #fig.write("</div>")
        for html_obj in viz_objects["direct html"]:
            fig.write(html_obj)
        
        fig.write("<div><small>"+datetime.now().strftime("%d. %m. %Y %H:%M:%S")+"</small></div>")
        
        with open("./script.js", "r") as f:
            js = f.readlines()
            fig.writelines(js)
        
        fig.write("</body> </html>\n")
    

#### CRAWLER ####
def load_edgar(path, file_format=data_loader.Convertions.JSON_TO_DICT):
    dator = data_loader.My_dataset(max_dataset_size=3)
    dator.load_dataset(path = path, load_as = file_format)
    return dator.dataset

if __name__ == "__main__":
    main()
