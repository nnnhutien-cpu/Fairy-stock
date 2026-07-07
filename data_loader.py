import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
# Bổ sung import từ vnstock
from vnstock import listing_companies, stock_historical_data
from supabase import create_client, Client

# --- KẾT NỐI SUPABASE ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# BÙA CHÚ 1: Cất danh sách mã vào bộ nhớ ảo 1 ngày
@st.cache_data(ttl=86400) 
def get_all_tickers(exchange='all'):
    try:
        df = listing_companies()
        if exchange != 'all':
            df = df[df['comGroupCode'] == exchange]
        return df['ticker'].tolist()
    except:
        # Trả về danh sách dự phòng nếu vnstock lỗi
        return ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

# BÙA CHÚ 2: Cất dữ liệu giá CỔ PHIẾU vào bộ nhớ ảo (Dùng Supabase)
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=3650): 
    try:
        # Lấy từ Supabase
        response = supabase.table("stock_data").select("*").eq("ticker", ticker).execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Xử lý lại cột thời gian cho chuẩn chỉ
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Đổi tên cột cho khớp 100% với form code cũ của bạn
            df.rename(columns={
                'close_price': 'close',
                'volume': 'volume',
                'date': 'time'
            }, inplace=True)
            
            # Lọc theo số ngày (days_back)
            if days_back:
                 df = df.tail(days_back)
                 
            return df
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Loi lay du lieu Supabase ma {ticker}: {str(e)}")
        return pd.DataFrame()

# HÀM 3: Lấy dữ liệu VN-INDEX dài hạn (Đã đổi tên thành get_vnindex_data cho đúng)
@st.cache_data(ttl=3600, show_spinner=False) 
def get_stock_data(ticker, days_back=3650): 
    try:
        # Lấy từ Supabase
        response = supabase.table("stock_data").select("*").eq("ticker", ticker).execute()
        
        # --- [BẪY LỖI MỚI Ở ĐÂY] ---
        if response.data is None or len(response.data) == 0:
            print(f"Kho Supabase trống, chưa có dữ liệu cho mã {ticker}")
            return pd.DataFrame() # Trả về bảng trống, không gây lỗi web
        
        df = pd.DataFrame(response.data)
        
        # Kiểm tra nếu sau khi load mà DataFrame vẫn không có cột cần thiết (date)
        if 'date' not in df.columns:
            return pd.DataFrame()

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Đổi tên cột
        df.rename(columns={'close_price': 'close', 'volume': 'volume', 'date': 'time'}, inplace=True)
        
        if days_back:
             df = df.tail(days_back)
             
        return df
            
    except Exception as e:
        # Ép kiểu an toàn (đã bọc áo giáp)
        safe_error = str(e).encode('ascii', errors='ignore').decode('ascii')
        print(f"Loi lay du lieu Supabase ma {ticker}: {safe_error}")
        return pd.DataFrame() # Trả về bảng trống để main.py xử lý bằng st.warning

# HÀM 4: Lấy dữ liệu VN-INDEX trong ngày (Thêm vào để main.py không bị lỗi ImportError)
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
