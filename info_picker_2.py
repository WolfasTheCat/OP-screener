# -*- coding: utf-8 -*-
"""
Created on Sat Apr 27 14:53:53 2024

@author: chodo
"""


from sec_edgar_api import EdgarClient

import screener_information_picker as picky

edgar = EdgarClient(user_agent="<Sample Company Name> <Admin Contact>@<Sample Company Domain>")
cik = 789019#MSFT
submission = edgar.get_submissions(cik=str(cik))


