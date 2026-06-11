import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# 🔑 ĐÃ THÊM: Import hàm stock_intraday_data để trị bệnh kẹt dữ liệu
from vnstock import stock_historical_data, listing_companies, stock_intraday_data

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

# BÙA CHÚ 2: Cất dữ liệu giá vào bộ nhớ ảo 1 giờ
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=3650): # Lấy lùi về 3650 ngày (10 năm)
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

# [CẬP NHẬT MỚI] Hàm 4: Lấy dữ liệu VN-INDEX trong ngày (Lai ghép Lịch sử + Real-time chống kẹt)
@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    try:
        # 1. Cào dữ liệu Khung 1 Phút để lấy "Sườn của Hôm Qua"
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        df_hist = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution='1', type='index')
        
        if df_hist is not None and not df_hist.empty:
            df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
            df_hist['time'] = pd.to_datetime(df_hist['time'])
            
            # Chỉ lấy 3 cột cốt lõi để chuẩn bị ghép nối
            cols_hist = [c for c in ['time', 'close', 'volume'] if c in df_hist.columns]
            df_hist = df_hist[cols_hist]
        else:
            df_hist = pd.DataFrame()

        # 2. Cào dữ liệu Tick Real-time để lấy "Dòng máu của Hôm Nay" (Không bao giờ kẹt)
        df_rt = stock_intraday_data(symbol='VNINDEX', page_num=0, page_size=5000)
        
        if df_rt is not None and not df_rt.empty:
            df_rt.columns = [str(c).lower().strip() for c in df_rt.columns]
            
            # Đồng bộ tên cột
            df_rt = df_rt.rename(columns={'price': 'close', 'matchvolume': 'volume', 'v': 'volume', 'c': 'close'})
            cols_rt = [c for c in ['time', 'close', 'volume'] if c in df_rt.columns]
            df_rt = df_rt[cols_rt]
            
            # Gắn ngày hiện tại vào
            today_str = datetime.now().strftime('%Y-%m-%d ')
            df_rt['time'] = pd.to_datetime(today_str + df_rt['time'].astype(str))
            df_rt = df_rt.sort_values('time', ascending=True)
            
            # Xóa sạch dữ liệu bị trễ của hôm nay trong bảng lịch sử
            if not df_hist.empty:
                df_hist = df_hist[df_hist['time'].dt.date != datetime.now().date()]
            
            # Nối 2 bảng lại thành 1 dòng thời gian hoàn hảo
            df_final = pd.concat([df_hist, df_rt], ignore_index=True)
            return df_final
        else:
            return df_hist

    except Exception as e:
        print("Lỗi get_intraday_vnindex:", e)
        return pd.DataFrame()
