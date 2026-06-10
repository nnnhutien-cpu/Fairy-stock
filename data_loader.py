import streamlit as st
from vnstock import stock_historical_data, listing_companies
import pandas as pd
from datetime import datetime, timedelta

# BÙA CHÚ 1: Cất danh sách mã vào bộ nhớ ảo 1 ngày
@st.cache_data(ttl=86400) 
def get_all_tickers(exchange='all'):
    # Code lấy danh sách mã của bạn ở đây...
    df = stock_listing()
    return df['ticker'].tolist()

# BÙA CHÚ 2: Cất dữ liệu giá 365 ngày vào bộ nhớ ảo 1 giờ
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=365):
    # Code cào dữ liệu của bạn ở đây...
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution="1D", type="stock")
        return df
    except:
        return None
