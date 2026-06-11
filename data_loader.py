import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import stock_historical_data, listing_companies

# BÙA CHÚ 1: Cất danh sách mã vào bộ nhớ ảo 1 ngày
@st.cache_data(ttl=86400) 
def get_all_tickers(exchange='all'):
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

# Hàm 3: Lấy dữ liệu VN-INDEX dài hạn (để main.py không bị lỗi)
@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(days_back=365):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution="1D", type="index")
        return df
    except:
        return None

# [ĐÃ SỬA] Hàm 4: Lấy dữ liệu VN-INDEX trong ngày (Khung 1 Phút)
@st.cache_data(ttl=60, show_spinner=False) # Lưu Cache 60 giây để web tự động nhảy số Real-time
def get_intraday_vnindex():
    try:
        # Lấy lùi lại 5 ngày để chắc chắn luôn có dữ liệu của Hôm Qua (trừ hao T7, CN)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        
        # Dùng resolution='1' để cào nến 1 phút
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
        
    return pd.DataFrame() # Nếu rớt mạng thì trả về bảng rỗng để web không sập
