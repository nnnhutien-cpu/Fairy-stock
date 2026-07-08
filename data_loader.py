import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import Vnstock

# Danh sách dự phòng nếu xui xẻo cả 3 CTCK cùng sập API
FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

def _normalize(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    if 'date' in df.columns and 'time' not in df.columns:
        df.rename(columns={'date': 'time'}, inplace=True)
        
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
        # LỌC MÚI GIỜ (TZ-NAIVE): Xóa timezone để không bị lỗi crash khi trừ ngày tháng ở main.py
        if getattr(df['time'].dt, 'tz', None) is not None:
            df['time'] = df['time'].dt.tz_localize(None)
            
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    if 'time' in df.columns:
        df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        
    return df

def _fetch_yahoo(symbol, start, end):
    try:
        import yfinance as yf
        # FIX LỖI: VNINDEX trên Yahoo tên là ^VNINDEX, không phải VNINDEX.VN
        yf_symbol = "^VNINDEX" if symbol == "VNINDEX" else f"{symbol}.VN"
        
        df = yf.download(yf_symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
            
        df = df.reset_index()
        # Xử lý Multi-Index cột của bản yfinance mới nhất
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.columns = [str(c).lower().strip() for c in df.columns]
        
        if 'date' in df.columns:
            df.rename(columns={'date': 'time'}, inplace=True)
            
        return _normalize(df)
    except Exception:
        return pd.DataFrame()

def _fetch(symbol, start, end, interval):
    # CƠ CHẾ DỰ PHÒNG: Thử lần lượt các nguồn, VCI và TCBS ổn định nhất
    sources = ['VCI', 'TCBS', 'KBS']
    
    for src in sources:
        try:
            df = Vnstock().stock(symbol=symbol, source=src).quote.history(
                start=start, end=end, interval=interval
            )
            if df is not None and not df.empty:
                return _normalize(df)
        except Exception:
            continue # Nếu lỗi API CTCK này, nhảy sang thử CTCK khác
            
    # Nếu cả 3 nguồn nội địa đều sập, cầu cứu Yahoo Finance
    if interval == '1D':
        return _fetch_yahoo(symbol, start, end)
        
    return pd.DataFrame()

@st.cache_data(ttl=86400) # Lưu cache danh sách mã trong 24h
def get_all_tickers(exchange='all'):
    try:
        # VCI cho hàm all_symbols() rất ổn định và trả về danh sách đầy đủ ~1525 mã
        stock_api = Vnstock().stock(symbol='ACB', source='VCI')
        try:
            df = stock_api.listing.all_symbols()
        except Exception:
            df = stock_api.listing.symbols_by_exchange() # Hàm dự phòng của vnstock

        df.columns = [str(c).lower().strip() for c in df.columns]
        
        # Tìm cột phân loại (Stock, Bond, CW...) để chỉ lấy cổ phiếu
        type_col = next((c for c in df.columns if 'type' in c), None)
        if type_col:
            df = df[df[type_col].astype(str).str.upper().isin(['STOCK', 'CP', 'CỔ PHIẾU'])]
            
        if 'exchange' in df.columns:
            df = df[df['exchange'].astype(str).str.upper().isin(['HOSE', 'HSX', 'HNX', 'UPCOM'])]
            if exchange != 'all':
                tgt = ['HOSE', 'HSX'] if str(exchange).upper() in ('HOSE', 'HSX') else [str(exchange).upper()]
                df = df[df['exchange'].astype(str).str.upper().isin(tgt)]
                
        col = 'symbol' if 'symbol' in df.columns else ('ticker' if 'ticker' in df.columns else None)
        
        if col:
            lst = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
            if lst:
                return lst
    except Exception:
        pass
        
    # Chỉ khi mạng rớt sạch thì mới phải dùng 10 mã dự bị
    return FALLBACK_TICKERS

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=200):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch(ticker, start_date, end_date, '1D')

@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=365):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch('VNINDEX', start_date, end_date, '1D')

@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    df = _fetch('VNINDEX', start_date, end_date, '1m')
    if not df.empty:
        return df
    return pd.DataFrame()
