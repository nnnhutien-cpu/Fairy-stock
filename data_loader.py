import streamlit as st
# Đã bổ sung thêm stock_intraday_data để lấy dữ liệu trong ngày
from vnstock import stock_historical_data, listing_companies, stock_intraday_data
import pandas as pd
from datetime import datetime, timedelta

# BÙA CHÚ 1: Cất danh sách mã vào bộ nhớ ảo 1 ngày
@st.cache_data(ttl=86400) 
def get_all_tickers(exchange='all'):
    # [ĐÃ SỬA] Đổi thành đúng hàm listing_companies() của bản 0.2.8.2
    try:
        df = listing_companies()
        # Lọc theo sàn nếu người dùng chọn
        if exchange != 'all':
            df = df[df['comGroupCode'] == exchange]
        return df['ticker'].tolist()
    except:
        return []

# BÙA CHÚ 2: Cất dữ liệu giá 365 ngày vào bộ nhớ ảo 1 giờ
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=365):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution="1D", type="stock")
        return df
    except:
        return None

# [MỚI THÊM] Hàm 3: Lấy dữ liệu VN-INDEX dài hạn (để main.py không bị lỗi)
@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(days_back=365):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution="1D", type="index")
        return df
    except:
        return None

# [MỚI THÊM] Hàm 4: Lấy dữ liệu VN-INDEX trong ngày (Intraday)
@st.cache_data(ttl=300, show_spinner=False) # Lưu Cache 5 phút
def get_intraday_vnindex():
    try:
        df = stock_intraday_data(symbol='VNINDEX', page_num=0, page_size=5000)
        return df
    except:
        return None
