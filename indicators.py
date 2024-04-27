# -*- coding: utf-8 -*-
"""
Created on Fri Feb 18 21:47:18 2022

@author: Jan Chodora

Indicators of technical analysis.
"""
# SMA   -
# EMA   -
# RSI   -
# CCI   -
# ATR   -
# ADX   -


def SMA(data, n):
    """
    Calculates a simple moving average for given array of numbers by step n.
    :param data: array of numbers
    :param n: size of step
    :return: SMA of data
    """
    sma_of_data = []
    ix = 0
    suma = 0
    while ix < n:
        suma += data[ix]
        ix += 1
    while ix < len(data):
        sma_of_data.append(suma/n)
        suma -= data[ix-n]
        suma += data[ix]
        ix += 1
    return sma_of_data


def EMA(data, n):
    """
    Calculates a exponentional moving average for given array of numbers by step n.
    :param data: array of numbers
    :param n: size of step
    :return: EMA of data
    """
    # Smoothing is a constant, which is usualy set to the value of 2
    SMOOTHING = 2
    # k = SMOOTHING / (1+n)
    k = SMOOTHING/(1+n)
    ema_of_data = []
    ix = n
    while ix < len(data):
        ema = 0
        for i in range(n):
            # EMA[i] = x[i] * k + EMA[i-1] * (1-k)
            ema = data[ix-n+i] * k + ema*(1-k)
        ema_of_data.append(ema)
        ix += 1
    return ema_of_data


def RSI(data, n):
    """
    Calculates RSI for given set of data by step n.
    :param data: array of numbers - close values of the market
    :param n: size of step, usualy 9, 14 or 26 days
    :return: RSI of data
    """
    rsi_of_data = []
    
    ix = n+1
    while ix < len(data):
        suma_gain = 0
        cnt_gain = 0
        suma_loss = 0
        cnt_loss = 0
        for i in range(n):
            if data[ix-n+i] > data[ix-n+i-1]:#gain
                suma_gain += data[ix-n+i] - data[ix-n+i-1]
                cnt_gain += 1
            else:
                suma_loss += data[ix-n+i-1] - data[ix-n+i]
                cnt_loss += 1
        gain = 0
        loss = 1
        if suma_loss != 0 and cnt_loss != 0:
            loss = suma_loss / cnt_loss
        
        if suma_gain != 0 and cnt_gain != 0:
            gain = suma_gain / cnt_gain
        rsi = 100 - 100/(1 + gain/loss)
        rsi_of_data.append(rsi)
        ix += 1
    return rsi_of_data


def CCI(High, Low, Close, n=20, prnt_details = False):
    """
    Calculates CCI for given set of data (High, Low, Close) by step n.
    This indicator is usualy used on commodity market.
    :param High: array of numbers - high values of the market
    :param Low: array of numbers - low values of the market
    :param Close: array of numbers - close values of the market
    :param n: size of step, typicaly used n = 20
    :return: CCI of data
    """
    # CCI = (TypicalPrice - SMA) / (0.015 * MeanDeviation)
    # TypicalPrice = Sum^n((High+Low+Close)/3)
    # MeanDeviation = (Sum^n(|TypicalPrice - SMA|)/n)
    cci_of_data = []
    TypicalPrice_of_data = TypicalPrice(High, Low, Close, n)
    sma_of_data = SMA(TypicalPrice_of_data, n)
    if prnt_details:
        print("TP",len(TypicalPrice_of_data))
        print("High",len(High))
        print("SMA",len(sma_of_data))
    ix = 0
    MeanDev_sum = 0
    for ix in range(n-1):
        MeanDev_sum += abs(TypicalPrice_of_data[ix] - sma_of_data[ix])
    ix+=1
    cci = 0
    while ix < len(sma_of_data):
        MeanDev_sum += abs(TypicalPrice_of_data[ix] - sma_of_data[ix])
        if ix % n == 0 or True:
            MeanDeviation = MeanDev_sum / n
            if MeanDeviation != 0:
                cci = (TypicalPrice_of_data[ix] - sma_of_data[ix]) / (0.015 * MeanDeviation)
            cci_of_data.append(cci)
        ix += 1
        MeanDev_sum -= abs(TypicalPrice_of_data[ix-n] - sma_of_data[ix-n])
    return cci_of_data


def TypicalPrice(High, Low, Close, n):
    """
    Calculates typical price for given set of data (High, Low, Close) by step n.
    This is only a partial calculation not an indicator on its own.
    Typical price is used to calculate CCI.
    :param High: array of numbers - high values of the market
    :param Low: array of numbers - low values of the market
    :param Close: array of numbers - close values of the market
    :param n: size of step
    :return: typical price of data
    """
    TypicalPrice_of_data = []
    ix = 0
    suma = 0
    for ix in range(n-1):
        suma += High[ix] + Low[ix] + Close[ix]
    ix+=1
    while ix < len(High):
        suma += High[ix] + Low[ix] + Close[ix]
        TypicalPrice = suma/3
        TypicalPrice_of_data.append(TypicalPrice)
        
        ix += 1
        suma -= High[ix-n] + Low[ix-n] + Close[ix-n]
    return TypicalPrice_of_data



def ATR(High, Low, Close, n):
    """
    Calculates ATR for given set of data (High, Low, Close) by step n.
    This indicator is usualy used on commodity market.
    :param High: array of numbers - high values of the market
    :param Low: array of numbers - low values of the market
    :param Close: array of numbers - close values of the market
    :param n: size of step, usualy 14 days
    :return: ATR of data
    """
    ix = 1
    atr_of_data = []
    suma = 0
    while ix < n:
        suma += TR(High[ix], Low[ix], Close[ix-1])
        ix += 1
    
    while ix < len(High):
        suma += TR(High[ix], Low[ix], Close[ix-1])
        atr = suma / n
        atr_of_data.append(atr)
        ix += 1
        suma -= TR(High[ix-n], Low[ix-n], Close[ix-n-1])
    return atr_of_data


def TR(high, low, previous_close):
    """
    Calculates TR for given set of data (high, low, close).
    :param high: highest value of todays market
    :param low: lowest value of todays market
    :param close: value on which market closed the day before
    :return: TR of data
    """
    return max(high - low, abs(high - previous_close), abs(low - previous_close))



def ADX(High, Low, Close, n):
    """
    ADX
    :param n: might be 14 (used by its creator Wilder)
    """
    atr = ATR(High, Low, Close, n)
    
    up_down_moves = UpDownMoves(High, Low)
    DM_up = up_down_moves[0]
    DM_down = up_down_moves[1]
    
    DI_up = DI(SMA(DM_up, n), atr)
    DI_down = DI(SMA(DM_down, n), atr)
    
    subtr_DI = absSubtraction(DI_up, DI_down)
    sma_of_abs_DIs = SMA(subtr_DI, n)
    
    adx_of_data = []
    
    for ix in range(min(len(sma_of_abs_DIs), len(DI_up), len(DI_down))):
        adx = 100 * sma_of_abs_DIs[ix] / (DI_up[ix] + DI_down[ix])
        adx_of_data.append(adx)
    return adx_of_data


def UpDownMoves(High, Low):
    """
    :return: (UpMoves, DownMoves) a set of 2 arrays, first of up moves, second of down moves
    """
    up_moves_of_data = []
    down_moves_of_data = []
    ix = 1
    while ix < len(High):
        up_move = High[ix] - High[ix-1]
        down_move = Low[ix-1] - Low[ix]
        DM_up = 0
        DM_down = 0
        if up_move > down_move and up_move > 0:
            DM_up = up_move
            
        if down_move > up_move and down_move > 0:
            DM_down = down_move
        
        up_moves_of_data.append(DM_up)
        down_moves_of_data.append(DM_down)
        ix += 1
    return (up_moves_of_data,down_moves_of_data)


def DI(data_preprocessed, atr):
    """
    :param data:_preprocessed moving average of original data
    :param atr: ATR of original data
    :return: DI of given data, where DI_i = 100 * (SMA(data)_i / ATR_i)
    """
    ix = 0
    stop = min(len(data_preprocessed), len(atr))
    di_of_data = []
    while ix < stop:
        # DI_i = 100 * (SMA(data)_i / ATR_i)
        di = 100 * data_preprocessed[ix] / atr[ix]
        di_of_data.append(di)
        ix += 1
    return di_of_data


def absSubtraction(DI_up, DI_down):
    """
    :return: array which contains subtracted values of the two arrays in absolute value
    """
    subtr_of_data = []
    for ix in range(min(len(DI_up), len(DI_down))):
        subtr_of_data.append(abs(DI_up[ix] - DI_down[ix]))
    return subtr_of_data
