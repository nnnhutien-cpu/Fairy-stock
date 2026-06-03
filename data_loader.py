from vnstock import stock_historical_data, listing_companies
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd

def get_vn_time():
    """Hàm ép hệ thống dùng đồng hồ Việt Nam (GMT+7)"""
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))

def get_stock_data(symbol, days_back=365):
    """Cào dữ liệu lịch sử cổ phiếu (Lấy 1 năm để đủ vẽ Mây Ichimoku)"""
    now_vn = get_vn_time()
    end_date = now_vn.strftime('%Y-%m-%d')
    start_date = (now_vn - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=symbol, 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="1D", type="stock")
        return df
    except Exception as e:
        return None

def get_vnindex_data():
    now_vn = get_vn_time()
    end_date = now_vn.strftime('%Y-%m-%d')
    start_date = (now_vn - timedelta(days=7)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution="1D", type="index")
        return df
    except Exception as e:
        return None

@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    """Lấy danh sách mã chứng khoán"""
    try:
        df = listing_companies()
        if exchange != 'all':
            df = df[df['comGroupCode'] == exchange]
        return df['ticker'].tolist()
    except Exception as e:
        return ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

def get_intraday_vnindex():
    """Cào dữ liệu VN-INDEX khung 5 phút (Hàm này bị thiếu gây lỗi nãy giờ)"""
    now_vn = get_vn_time()
    start_date = (now_vn - timedelta(days=5)).strftime('%Y-%m-%d')
    end_date = now_vn.strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="5", 
                                   type="index")
        return df
    except Exception as e:
        return None
