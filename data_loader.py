import time
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import Vnstock

FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]
SOURCE = 'VCI'   # nguồn free ổn định nhất; đổi 'TCBS' nếu VCI lỗi


def _normalize(df):
    """Chuẩn hóa tên cột + kiểu dữ liệu cho khớp toàn hệ thống."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if 'date' in df.columns and 'time' not in df.columns:
        df.rename(columns={'date': 'time'}, inplace=True)
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'time' in df.columns:
        df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return df


def _match_exchange(val, target):
    """So khớp sàn, coi HOSE và HSX là một."""
    val = str(val).upper()
    target = str(target).upper()
    if target in ('HOSE', 'HSX'):
        return val in ('HOSE', 'HSX')
    return val == target


# HÀM 1: Danh sách mã theo sàn (đã loại mã hủy niêm yết + phi cổ phiếu)
@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    try:
        listing = Vnstock().stock(symbol='ACB', source=SOURCE).listing
        df = listing.symbols_by_exchange()
        df.columns = [str(c).lower().strip() for c in df.columns]

        # Chỉ giữ cổ phiếu (loại trái phiếu, CCQ, phái sinh...)
        if 'type' in df.columns:
            df = df[df['type'].astype(str).str.upper() == 'STOCK']

        # Chỉ giữ 3 sàn đang giao dịch (loại DELISTED = đã hủy niêm yết)
        if 'exchange' in df.columns:
            df = df[df['exchange'].astype(str).str.upper().isin(['HOSE', 'HSX', 'HNX', 'UPCOM'])]
            if exchange != 'all':
                df = df[df['exchange'].apply(lambda x: _match_exchange(x, exchange))]

        col = 'symbol' if 'symbol' in df.columns else ('ticker' if 'ticker' in df.columns else None)
        if col is None:
            return FALLBACK_TICKERS

        tickers = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
        return tickers if tickers else FALLBACK_TICKERS
    except Exception:
        return FALLBACK_TICKERS


# HÀM 2: Dữ liệu cổ phiếu (retry 3 lần, chỉ cache khi có data thật)
@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=3650):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    for _ in range(3):
        try:
            stock = Vnstock().stock(symbol=ticker, source=SOURCE)
            df = stock.quote.history(start=start_date, end=end_date, interval='1D')
            norm = _normalize(df)
            if not norm.empty:
                return norm
        except Exception:
            pass
        time.sleep(0.4)
    return pd.DataFrame()


# HÀM 3: VN-INDEX dài hạn
@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=3650):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    for _ in range(3):
        try:
            idx = Vnstock().stock(symbol='VNINDEX', source=SOURCE)
            df = idx.quote.history(start=start_date, end=end_date, interval='1D')
            norm = _normalize(df)
            if not norm.empty:
                return norm
        except Exception:
            pass
        time.sleep(0.4)
    return pd.DataFrame()


# HÀM 4: VN-INDEX trong ngày (nến 1 phút)
@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    for _ in range(3):
        try:
            idx = Vnstock().stock(symbol='VNINDEX', source=SOURCE)
            df = idx.quote.history(start=start_date, end=end_date, interval='1m')
            if df is not None and len(df) > 0:
                df = df.copy()
                df.columns = [str(c).lower().strip() for c in df.columns]
                return df
        except Exception:
            pass
        time.sleep(0.4)
    return pd.DataFrame()
