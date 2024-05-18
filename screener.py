# -*- coding: utf-8 -*-
"""
Created on Wed Mar 27 12:17:02 2024
                                                                                                                                                                                                                                                                
@author: chodo
"""

import yfinance as yf

import plotly.express as plx
import plotly.offline as plo

import plotly.graph_objects as plgo
import plotly.subplots as plsub

from datetime import datetime

import indicators
import const

import pickle

def main():
    viz_objects = {"visualization":{},"direct html":[]}
    
    # As JSON:
    #edgar_reports = load_edgar(path="../edgar-crawler-main/datasets/EXTRACTED_FILINGS/")
    #for k in edgar_reports:
    #    text_area = "<div>"+edgar_reports[k]["item_6"][:300]+"</div>"
    #    viz_objects["direct html"].append(text_area)
    
    data = yf.download("^SPX", start="2018-01-01", end=datetime.now().strftime("%Y-%m-%d"))
    #viz_objects["visualization"].append(plx.bar(x=data.index, y=data["Close"]))
    
    graph_title = "S&P 500 Index"
    #, "yaxis":"Price [USD]", "xaxis":"Time"
    
    
    #original#candle_graph = plgo.Figure( plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"]), layout=graph_layout )
    

    price_title = "Price Developement"
    price_graph = price_graphs(data, title=price_title+" of "+graph_title)
    
    
    #histogram_sub   = plgo.Histogram(   x=data.index, y=data["Volume"], name="Histogram", visible="legendonly")
    
    
    viz_objects["visualization"][price_title] = price_graph
    ita_title = "Indicators of Technical Analysis"
    viz_objects["visualization"][ita_title] = hover_subplots(data, class_title=ita_title, graph_title=graph_title)
    viz_objects["visualization"]["Fundamental Analysis"] = PE_graph()
    multiple_graphs_on_page(viz_objects)
    
def hover_subplots(data, class_title, graph_title):
    layout = dict(
        hoversubplots="axis",
        title=class_title+" for "+graph_title,
        hovermode="x",
        grid=dict(rows=3, columns=1),
        coloraxis=dict(colorscale='solar_r', showscale=False, colorbar_orientation="h")
        
    )
    
    plots = [plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"], name="Price", xaxis="x", yaxis="y")]
    #plots.append(plgo.Line(x=data.index, y= data["Close"], name="Close", xaxis="x", yaxis="y", visible="legendonly"))
    
    ma_range = (10, 20, 30, 50)
    for sma_n in ma_range:
        close_SMA = indicators.SMA(data["Close"], sma_n)
        plots.append(
            plgo.Line(x=data.index[len(data["Close"])-len(close_SMA):], y= close_SMA, name="SMA("+str(sma_n)+")", xaxis="x", yaxis="y", visible=("legendonly" if sma_n!=20 else True)))
    
    for ema_n in ma_range:
        close_EMA = indicators.EMA(data["Close"], ema_n)
        plots.append(
            plgo.Line(x=data.index[len(data["Close"])-len(close_EMA):], y= close_EMA, name="EMA("+str(ema_n)+")", xaxis="x", yaxis="y", visible="legendonly" if ema_n!=20 else True))
    num_plots_1st = len(plots)
    for rsi_n in (9, 14, 26):
        close_RSI_n = indicators.RSI(data["Close"], rsi_n)
        plots.append(
            plgo.Line(x=data.index[len(data["Close"])-len(close_RSI_n):], y= close_RSI_n, name="RSI("+str(rsi_n)+")", xaxis="x", yaxis="y2", visible=("legendonly" if rsi_n!=14 else True)))
    num_plots_2nd = len(plots) - num_plots_1st
    plots.append(
        plgo.Bar(x=data.index, y=data["Volume"], name="Volume", xaxis="x", yaxis="y3", marker=dict(color=data["Volume"], coloraxis="coloraxis")))
    
    fig = plgo.Figure(data=plots, layout=layout)
    fig.update_layout(title_text=class_title+" for "+graph_title,
                      yaxis=dict(title="Price [USD]", overlaying="y", rangemode="tozero"),
                      yaxis2=dict(title="RSI", overlaying="y2"),
                      yaxis3=dict(title="Volume", overlaying="y3", rangemode="tozero"),
                      xaxis=dict(overlaying="x", rangeslider_visible=False))
    fig.update_legends(title_text=class_title)
    fig.update_xaxes(# time buttons
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                #dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1y", step="year", stepmode="backward"),
                dict(step="all")
            ])
        )#, rangeslider_visible=True, rangeslider_thickness=0.15# default 0.15, rangeslider_bordercolor="black"
        )
    # !! fixed indexes
    fig.data[0].increasing.line.color = "rgba(0,239,0, 0.5)"
    fig.data[0].increasing.fillcolor = "rgba(0,239,0, 0.5)"
    
    fig.data[0].decreasing.line.color = "rgba(127,127,0, 1)"
    fig.data[0].decreasing.fillcolor = "rgba(127,127,0, 1)"
    
    clrs = ['#000000', '#D8D844', '#909000', '#A4A400', '#707000', '#505000', '#BFBF00', '#343400']
    for i in range(1, num_plots_1st, 1):
        fig['data'][i]['line']['color']=clrs[i-1]
    for i in range(0, num_plots_2nd, 1):
        fig['data'][num_plots_1st+i]['line']['color']=clrs[i]
    
    fig.update_yaxes(fixedrange=False)# for y and box zoom
    return fig
    
def price_graphs(data, title):
    #price_subs = moving_averages_subgraphs(data)
    
    price_candle_sub = plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"], name="Candlestick")
    #price_subs.append(price_candle_sub)
    
    price_graph = plgo.Figure(data=price_candle_sub, layout={"title":{"text":title}, "xaxis_title":{"text":"Time"}, "yaxis_title":{"text":"Price USD"}} )
    price_graph.update_yaxes(fixedrange=False)# fixing the y-range of the graph <3
    return price_graph

def PE_graph(company_ticker="MSFT"):
    with open(company_ticker+"D_PE"+".json", 'rb') as f:
        PE_data = pickle.load(f)
    #plx.Figure( )
    #plx.Figure( )
    fig = plsub.make_subplots()
    for k in PE_data:
         fig.add_trace(plgo.Scatter(x=PE_data[k]["date"], y= PE_data[k]["value"], name=k))
    fig.update_layout(title_text="P/E Ratio for "+company_ticker)
    fig.update_legends(title_text="Earnings Per Share Diluted [USD]")
    #fig = plx.scatter(x=PE_data["date"], y= PE_data["value"])
    return fig

"""
def candlesticks_positive_negative(data):
    data['change'] = data['Close'] - data['Open']
    data_up = data[data['change']>0]
    data_down = data[data['change']<=0]
    cs_pl_go   = [plgo.Candlestick(x=data_up.index, open=data_up["Open"], high=data_up["High"], low=data_up["Low"], close=data_up["Close"], name="Positive Days", xaxis="x", yaxis="y"),
               plgo.Candlestick(x=data_down.index, open=data_down["Open"], high=data_down["High"], low=data_down["Low"], close=data_down["Close"], name="Negative Days", xaxis="x", yaxis="y")]
    return cs_pl_go

fig.data[1].increasing.fillcolor = 'rgba(0,255,0, 255)'
fig.data[1].increasing.line.color = 'rgba(0,127,0,255)'
fig.data[1].decreasing.fillcolor = 'rgba(0,0,0,0)'
fig.data[1].decreasing.line.color = 'rgba(0,0,0,0)'

fig.data[2].increasing.fillcolor = 'rgba(0,0,0,0)'
fig.data[2].increasing.line.color = 'rgba(0,0,0,0)'
fig.data[2].decreasing.fillcolor = 'rgba(127,0,0,255)'
fig.data[2].decreasing.line.color = 'rgba(255,0,0,255)'
"""
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
    
if __name__ == "__main__":
    main()
