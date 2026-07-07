import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import listing_companies, stock_historical_data

# ĐÃ XÓA TOÀN BỘ KẾT NỐI SUPABASE THEO YÊU CẦU

# HÀM 1: Cất danh sách mã vào bộ nhớ ảo
@st.cache_data(ttl=86400) 
def get_all_tickers(exchange='all'):
    try:
        df = listing_companies()
        if exchange != 'all':
            df = df[df['comGroupCode'] == exchange]
        return df['ticker'].tolist()
    except:
        return ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

# HÀM 2: Lấy dữ liệu CỔ PHIẾU trực tiếp từ Vnstock (Bỏ qua Supabase)
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=3650): 
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df is not None and not df.empty:
            # Đảm bảo tên cột khớp 100% với form code cũ của bạn
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'date' in df.columns and 'time' not in df.columns:
                 df.rename(columns={'date': 'time'}, inplace=True)
                 
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time')
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# HÀM 3: Lấy dữ liệu VN-INDEX dài hạn trực tiếp từ Vnstock
@st.cache_data(ttl=3600, show_spinner=False) 
def get_vnindex_data(ticker="VNINDEX", days_back=3650): 
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution='1D', type='index')
        
        if df is not None and not df.empty:
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'date' in df.columns and 'time' not in df.columns:
                 df.rename(columns={'date': 'time'}, inplace=True)
                 
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time')
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# HÀM 4: Lấy dữ liệu VN-INDEX trong ngày
@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution='1', type='index')
        if df is not None and not df.empty:
            df.columns = [str(c).lower().strip() for c in df.columns]
            return df
    except Exception:
        pass
    return pd.DataFrame()
