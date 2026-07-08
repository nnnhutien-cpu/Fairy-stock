import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import listing_companies, stock_historical_data

# ĐÃ XÓA TOÀN BỘ KẾT NỐI SUPABASE THEO YÊU CẦU

FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]


def _normalize(df):
    """Chuẩn hóa tên cột + kiểu dữ liệu cho khớp form code cũ."""
    if df is None or df.empty:
        return pd.DataFrame()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if 'date' in df.columns and 'time' not in df.columns:
        df.rename(columns={'date': 'time'}, inplace=True)
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
    # Ép các cột giá/khối lượng về số để tránh lỗi tính toán
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return df


# HÀM 1: Danh sách mã (cache 1 ngày)
@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    try:
        df = listing_companies()
        df.columns = [str(c).lower().strip() for c in df.columns]
        if 'ticker' not in df.columns:
            return FALLBACK_TICKERS
        # Chỉ giữ 3 sàn chính, loại dòng rác/không có mã
        if 'comgroupcode' in df.columns:
            df = df[df['comgroupcode'].isin(['HOSE', 'HNX', 'UPCOM'])]
            if exchange != 'all':
                df = df[df['comgroupcode'] == exchange]
        tickers = [str(t).strip().upper() for t in df['ticker'].dropna().tolist() if str(t).strip()]
        return tickers if tickers else FALLBACK_TICKERS
    except Exception:
        return FALLBACK_TICKERS


# HÀM 2: Dữ liệu cổ phiếu (cache 1 giờ)
@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=3650):
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = stock_historical_data(symbol=ticker, start_date=start_date,
                                   end_date=end_date, resolution='1D', type='stock')
        return _normalize(df)
    except Exception:
        return pd.DataFrame()


# HÀM 3: Dữ liệu VN-INDEX dài hạn (cache 1 giờ)
@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=3650):
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date,
                                   end_date=end_date, resolution='1D', type='index')
        return _normalize(df)
    except Exception:
        return pd.DataFrame()


# HÀM 4: VN-INDEX trong ngày (cache 60 giây)
@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        df = stock_historical_data(symbol='VNINDEX', start_date=start_date,
                                   end_date=end_date, resolution='1', type='index')
        if df is not None and not df.empty:
            df.columns = [str(c).lower().strip() for c in df.columns]
            return df
    except Exception:
        pass
    return pd.DataFrame()
