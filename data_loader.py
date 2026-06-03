from vnstock import stock_historical_data, listing_companies
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd

def get_vn_time():
    """Hàm ép máy chủ Mỹ phải dùng đồng hồ múi giờ Việt Nam (GMT+7)"""
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))

def get_stock_data(symbol, days_back=365):
    """Cào dữ liệu cổ phiếu (Lấy lùi lại 1 năm để đủ tính MA200)"""
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
    """Cào dữ liệu chỉ số VN-INDEX Real-time"""
    now_vn = get_vn_time()
    end_date = now_vn.strftime('%Y-%m-%d')
    start_date = (now_vn - timedelta(days=7)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="1D", type="index")
        return df
    except Exception as e:
        return None

@st.cache_data(ttl=86400) # Bộ nhớ đệm: Chỉ tải danh sách 1 lần/ngày cho nhẹ web
def get_all_tickers(exchange='all'):
    """Lấy danh sách mã chứng khoán theo sàn"""
    try:
        df = listing_companies()
        if exchange != 'all':
            df = df[df['comGroupCode'] == exchange] # Lọc HOSE, HNX, UPCOM
        return df['ticker'].tolist()
    except Exception as e:
        # Danh sách dự phòng nếu vnstock bảo trì
        return ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

@st.cache_data(ttl=300) # Bộ nhớ đệm tự làm mới sau 5 phút
def get_intraday_vnindex():
    """Lấy dữ liệu VN-INDEX khung 5 phút để vẽ biểu đồ thanh khoản"""
    now_vn = get_vn_time()
    # Lấy lùi lại 5 ngày để đảm bảo luôn có dữ liệu của ngày hôm qua (trừ T7, CN)
    start_date = (now_vn - timedelta(days=5)).strftime('%Y-%m-%d')
    end_date = now_vn.strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="5m", type="index")
        return df
    except Exception as e:
        return None
