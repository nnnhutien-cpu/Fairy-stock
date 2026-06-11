import streamlit as st
import pandas as pd
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
@st.cache_data(ttl=3600) # Lưu đệm 1 tiếng để web chạy mượt như chớp
def get_stock_data(ticker, days_back=365):
    try:
        # Gọi thẳng vào Supabase lấy dữ liệu của mã cổ phiếu
        # Bạn có thể kết hợp thêm logic ngày tháng (days_back) ở đây nếu cần, 
        # hoặc cứ lấy hết ra rồi Pandas sẽ tự xử lý.
        response = supabase.table("stock_data").select("*").eq("ticker", ticker).execute()
        
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Xử lý lại cột thời gian cho chuẩn chỉ
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Đổi tên cột cho khớp 100% với form code cũ của bạn
            # Để main.py không bị bỡ ngỡ
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
        st.error(f"Lỗi khi lấy dữ liệu Supabase mã {ticker}: {e}")
        return pd.DataFrame()
    return pd.DataFrame()
