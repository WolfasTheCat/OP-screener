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
    
    graph_title = "of S&P 500 Index"
    #, "yaxis":"Price [USD]", "xaxis":"Time"
    
    #original#candle_graph = plgo.Figure( plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"]), layout=graph_layout )
    price_title = "Price Developement "
    price_subs = []
    price_candle_sub = plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"], name="Candlestick")
    price_subs.append(price_candle_sub)
    
    for sma_n in (10, 20, 30, 50):
        close_SMA = indicators.SMA(data["Close"], sma_n)
        if sma_n != 20:
            price_sma_sub = plgo.Line(x=data.index[len(data["Close"])-len(close_SMA):], y= close_SMA, name="SMA("+str(sma_n)+")", visible="legendonly")
        else:
            price_sma_sub = plgo.Line(x=data.index[len(data["Close"])-len(close_SMA):], y= close_SMA, name="SMA("+str(sma_n)+")")
        price_subs.append(price_sma_sub)
    
    
    for ema_n in (10, 20, 30, 50):
        close_EMA = indicators.EMA(data["Close"], ema_n)
        if ema_n != 20:
            price_ema_sub = plgo.Line(x=data.index[len(data["Close"])-len(close_EMA):], y= close_EMA, name="EMA("+str(ema_n)+")", visible="legendonly")
        else:
            price_ema_sub = plgo.Line(x=data.index[len(data["Close"])-len(close_EMA):], y= close_EMA, name="EMA("+str(ema_n)+")")
        price_subs.append(price_ema_sub)

    
    price_graph = plgo.Figure( 
        data=price_subs, layout={"title":{"text":price_title+graph_title}, "xaxis_title":{"text":"Time"}, "yaxis_title":{"text":"Price USD"}} )
    viz_objects["visualization"][price_title] = price_graph
    
    
    rsi_title = "Relative Strength Index of Closing Price "
    rsi_subs = []
    for rsi_n in (9, 14, 26):
        close_RSI_n = indicators.RSI(data["Close"], rsi_n)
        if rsi_n != 14:
            analysis_price_rsi_sub = plgo.Line(x=data.index[len(data["Close"])-len(close_RSI_n):], y= close_RSI_n, name="RSI("+str(rsi_n)+")", visible="legendonly")
        else:
            analysis_price_rsi_sub = plgo.Line(x=data.index[len(data["Close"])-len(close_RSI_n):], y= close_RSI_n, name="RSI("+str(rsi_n)+")")
        rsi_subs.append(analysis_price_rsi_sub)
    rsi_graph = plgo.Figure( data= rsi_subs, layout={"title":{"text":rsi_title+graph_title}, "yaxis_title":{"text":"RSI"}, "xaxis_title":{"text":"Time"}} )
    viz_objects["visualization"][rsi_title] = rsi_graph
    
    """
    cci_title = "Commodity Channel Index of Closing Price "+graph_title
    cci_subs = []
    for cci_n in (10, 14, 20, 30, 50):
        price_CCI = indicators.CCI(High=data["High"], Low=data["Low"], Close=data["Close"], n=cci_n)
        if cci_n != 20:
            analysis_price_cci_sub = plgo.Line(x=data.index[len(data["Close"])-len(price_CCI):], y= price_CCI, name="CCI("+str(cci_n)+")", visible="legendonly")
        else:
            analysis_price_cci_sub = plgo.Line(x=data.index[len(data["Close"])-len(price_CCI):], y= price_CCI, name="CCI("+str(cci_n)+")")
        cci_subs.append(analysis_price_cci_sub)
    cci_graph = plgo.Figure( data= cci_subs, layout={"title":{"text":cci_title}, "yaxis_title":{"text":"CCI"}, "xaxis_title":{"text":"Time"}} )
    viz_objects["visualization"][cci_title] = cci_graph
    """
    
    volume_title = "Trade Volume Developement "
    bar_sub         = plgo.Bar(         x=data.index, y=data["Volume"], name="Bar chart")
    #histogram_sub   = plgo.Histogram(   x=data.index, y=data["Volume"], name="Histogram", visible="legendonly")
    volume_graph = plgo.Figure( 
        data=[ bar_sub
              #, histogram_sub
        ], layout={"title":{"text":volume_title+graph_title}, "yaxis_title":{"text":"Volume of Shares Traded"}, "xaxis_title":{"text":"Time"}} )
    viz_objects["visualization"][volume_title] = volume_graph
    
    
    #viz_objects["visualization"][candle_title] = candle_graph# not this way
    
    # plgo.Figure(candle_graph).show()
    
    multiple_graphs_on_page(viz_objects)



def multiple_graphs_on_page(viz_objects, file=const.RESULTING_FILE):
    fig = open(file,"w",encoding="utf8")# <3 \u2665
    fig.write("<html> <head> <title>Screener</title></head> <body>\n")
    include_js = True
    
    graphs = viz_objects["visualization"]
    fig.write("<h2>"+datetime.now().strftime("%d/%m/%Y %H:%M:%S")+"</h2>")
    for k in graphs:
        viz_plot = plo.plot(graphs[k], include_plotlyjs=include_js,output_type="div")
        
        
        fig.write(viz_plot)
        include_js = False
        
    for html_obj in viz_objects["direct html"]:
        fig.write(html_obj)
    fig.write("</body> </html>\n")
    

#### CRAWLER ####
def load_edgar(path, file_format=data_loader.Convertions.JSON_TO_DICT):
    dator = data_loader.My_dataset(max_dataset_size=3)
    dator.load_dataset(path = path, load_as = file_format)
    return dator.dataset

if __name__ == "__main__":
    main()
