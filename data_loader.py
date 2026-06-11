import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import stock_historical_data, listing_companies, stock_intraday_data

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

# BÙA CHÚ 2: Cất dữ liệu giá vào bộ nhớ ảo
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

# 🛡️ [ĐÃ CÁCH LY LỖI] Hàm 4: Lấy dữ liệu VN-INDEX trong ngày 
@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    df_hist = pd.DataFrame()
    df_rt = pd.DataFrame()
    
    # BƯỚC 1: Cố gắng lấy "Khung xương" lịch sử (Dù trễ nhưng rất ổn định)
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        df_h = stock_historical_data(symbol='VNINDEX', start_date=start_date, end_date=end_date, resolution='1', type='index')
        
        if df_h is not None and not df_h.empty:
            df_h.columns = [str(c).lower().strip() for c in df_h.columns]
            df_h['time'] = pd.to_datetime(df_h['time'])
            cols_hist = [c for c in ['time', 'close', 'volume'] if c in df_h.columns]
            df_hist = df_h[cols_hist]
    except Exception:
        pass # Lỗi thì bỏ qua, đi tiếp

    # BƯỚC 2: Cố gắng lấy "Dòng máu" Real-time nhảy số
    try:
        df_r = stock_intraday_data(symbol='VNINDEX', page_num=0, page_size=5000)
        
        if df_r is not None and not df_r.empty:
            df_r.columns = [str(c).lower().strip() for c in df_r.columns]
            df_r = df_r.rename(columns={'price': 'close', 'matchvolume': 'volume', 'v': 'volume', 'c': 'close'})
            cols_rt = [c for c in ['time', 'close', 'volume'] if c in df_r.columns]
            df_rt = df_r[cols_rt]
            
            today_str = datetime.now().strftime('%Y-%m-%d ')
            df_rt['time'] = pd.to_datetime(today_str + df_rt['time'].astype(str))
            df_rt = df_rt.sort_values('time', ascending=True)
    except Exception:
        pass # Lỗi intraday thì kệ, không được xóa mất dữ liệu lịch sử ở trên

    # BƯỚC 3: Ghép thông minh (Có gì dùng nấy)
    if not df_rt.empty and not df_hist.empty:
        # Nếu cả 2 đều chạy mượt: Gắn đồ thị real-time vào nối tiếp đồ thị hôm qua
        df_hist = df_hist[df_hist['time'].dt.date != datetime.now().date()]
        return pd.concat([df_hist, df_rt], ignore_index=True)
    elif not df_hist.empty:
        # Kịch bản phòng thủ: Nếu Real-time từ chối trả số VN-INDEX, vẫn hiện sườn Lịch sử
        return df_hist
    elif not df_rt.empty:
        return df_rt
    else:
        return pd.DataFrame()
