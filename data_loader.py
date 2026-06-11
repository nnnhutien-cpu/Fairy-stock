import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import stock_historical_data, listing_companies

# BÙA CHÚ 1: Cất danh sách mã vào bộ nhớ ảo 1 ngày
@st.cache_data(ttl=86400) 
def get_all_tickers(exchange='all'):
    try:
        df = listing_companies()
        if exchange != 'all':
            df = df[df['comGroupCode'] == exchange]
        return df['ticker'].tolist()
    except:
        return []

# BÙA CHÚ 2: Cất dữ liệu giá vào bộ nhớ ảo 1 giờ
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=3650): 
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution="1D", type="stock")
        return df
    except:
        return None

# Hàm 3: Lấy dữ liệu VN-INDEX dài hạn
@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(days_back=365):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution="1D", type="index")
        return df
    except:
        return None

# Hàm 4: Lấy dữ liệu VN-INDEX trong ngày (Bản chuẩn ổn định)
@st.cache_data(ttl=60, show_spinner=False) # Lưu cache 60 giây để tự động làm mới
def get_intraday_vnindex():
    try:
        # Lấy lùi lại 5 ngày để luôn có sườn Hôm Qua và Hôm Nay
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        
        df = stock_historical_data(
            symbol='VNINDEX', 
            start_date=start_date, 
            end_date=end_date, 
            resolution='1', 
            type='index'
        )
        if df is not None and not df.empty:
            df.columns = [str(c).lower().strip() for c in df.columns]
            return df
    except Exception:
        pass
        
    return pd.DataFrame()
