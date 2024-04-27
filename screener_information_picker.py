# -*- coding: utf-8 -*-
"""
Created on Wed Apr 24 12:27:13 2024

@author: chodo

Main task of this module will be on call with parameters,
 to retrieve specific object or topic related information
 out of it's corpus
"""

from sec_api import QueryApi# limited number of requests - unsustainable :(

#from sec_edgar_api import EdgarClient

import const

queryApi = QueryApi(api_key=const.EDGAR_API_KEY)

query = {
  "query": "ticker:MSFT AND filedAt:[2020-01-01 TO 2024-12-31] AND formType:\"10-Q\"",
  "from": "0",
  "size": "10",
  "sort": [{ "filedAt": { "order": "desc" } }]
}
filings = queryApi.get_filings(query)

results = find_info_in_doc(document=filings, find=["revenue", "gross", "margin", "financial", "msft-20240331", "17,080", "778", "cik", "htm"])
cik = int(results["cik"][0])

len(results["htm"])




def find_info_in_doc(document, find):
    stack = [document]
    results = {}
    low_find = [f.lower() for f in find]
    while len(stack) > 0:
        item = stack.pop()# !!! replacing the original variable
        if type(item) is dict:
            for k in item:
                low_k = k.lower()
                if low_k in low_find:#                              if A in B:
                    add_to_dict(results, key=k, item=item[k])#           Found
                    #results.append({k:item[k]})
                else:
                    skip_this_item = False
                    for f in low_find:
                        if f in low_k:#                             if B in A:
                            add_to_dict(results, key=k, item=item[k])#   Found
                            skip_this_item = True
                            #results.append({k:item[k]})
                    if not skip_this_item:
                        stack.append(item[k])
        elif type(item) is list:
            for i in range(len(item)):
                stack.append(item[i])
        else:
            if type(item) is str:
                item_lc = item.lower()
                for f in low_find:
                    if f in item_lc:
                        add_to_dict(results, key=f, item=item)#         Found
                        #results.append({f:item})
            #else:# continue
            #    #print(type(item))
    return results

def add_to_dict(dic, key, item):
    if key not in dic:
        dic[key] = [item]
    else:
        if item not in dic[key]:
            dic[key].append(item)



# print(filings)

    
"""  
import plotly.subplots as psub
def via_sub_plots():# in this form it can plot multiple graphs into one - if needed ;-)
    viz_objects = {"visualization":{},"direct html":[]}
    edgar_reports = load_edgar(path="../edgar-crawler-main/datasets/EXTRACTED_FILINGS/")
    for k in edgar_reports:
        text_area = "<div>"+edgar_reports[k]["item_1"][:1000]+"</div>"
        viz_objects["direct html"].append(text_area)
    
    downloaded_instrument = "^SPX"
    data = yf.download(downloaded_instrument, start="2020-01-01", end="2021-01-01")
    #viz_objects["visualization"].append(plx.bar(x=data.index, y=data["Close"]))
    
    
    fig = psub.make_subplots()
    
    
    candle_title = "SP500 index"# plgo.Figure( )
    candle_graph = plgo.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"]) 
    
    
    fig.add_trace(candle_graph)
    
    viz_objects["visualization"][candle_title] = fig
    
    # plgo.Figure(candle_graph).show()
    
    multiple_graphs_on_page(viz_objects)
 """
 
"""
def experiments():
    ######## PLOTLY  ########
    fig = plx.bar(x=["a", "b", "c"], y=[1, 3, 2])
    
    ######## YAHOO  ########
    # SP500 ^SPX nebo ^GSPC

#def load_current_prices():
    fig = plx.bar(x=["SPX500"], y=[data])
    fig.write_html('first_figure.html', auto_open=True)
    # seems like this way??
    #print(data.head())
"""
