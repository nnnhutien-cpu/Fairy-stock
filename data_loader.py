from vnstock import stock_historical_data, listing_companies
from datetime import datetime, timedelta
import streamlit as st

def get_stock_data(symbol, days_back=365):
    """Cào dữ liệu cổ phiếu (Lấy lùi lại 1 năm để đủ tính MA200)"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=symbol, 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="1D", type="stock")
        return df
    except Exception as e:
        return None

def get_vnindex_data():
    """Cào dữ liệu chỉ số VN-INDEX 7 ngày gần nhất"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
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
