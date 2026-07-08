import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from vnstock import Vnstock

FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]
SOURCES = ['KBS', 'VCI']
_API_TIMEOUT = 8   # giây tối đa chờ mỗi nguồn


def _normalize(df):
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


def _call_vnstock(symbol, src, start, end, interval):
    """Chạy trong thread — có thể bị cancel từ ngoài."""
    return Vnstock().stock(symbol=symbol, source=src).quote.history(
        start=start, end=end, interval=interval)


def _fetch_yahoo(symbol, start, end):
    try:
        import yfinance as yf
        df = yf.download(f"{symbol}.VN", start=start, end=end,
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.columns = [str(c).lower().strip() for c in df.columns]
        df.rename(columns={'date': 'time'}, inplace=True)
        return _normalize(df)
    except Exception:
        return pd.DataFrame()


def _fetch(symbol, start, end, interval):
    # 1. Thử KBS rồi VCI, mỗi nguồn có hard timeout _API_TIMEOUT giây
    for src in SOURCES:
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call_vnstock, symbol, src, start, end, interval)
                raw = fut.result(timeout=_API_TIMEOUT)
            if raw is not None and len(raw) > 0:
                return _normalize(raw)
        except (FuturesTimeout, Exception):
            continue
    # 2. Yahoo Finance fallback (chỉ daily)
    if interval == '1D':
        df = _fetch_yahoo(symbol, start, end)
        if not df.empty:
            return df
    return pd.DataFrame()


@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    for src in SOURCES:
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(
                    lambda s=src: Vnstock().stock(symbol='ACB', source=s)
                    .listing.symbols_by_exchange()
                )
                df = fut.result(timeout=15)
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'type' in df.columns:
                df = df[df['type'].astype(str).str.upper() == 'STOCK']
            if 'exchange' in df.columns:
                df = df[df['exchange'].astype(str).str.upper()
                        .isin(['HOSE', 'HSX', 'HNX', 'UPCOM'])]
                if exchange != 'all':
                    tgt = (['HOSE', 'HSX'] if str(exchange).upper()
                           in ('HOSE', 'HSX') else [str(exchange).upper()])
                    df = df[df['exchange'].astype(str).str.upper().isin(tgt)]
            col = ('symbol' if 'symbol' in df.columns
                   else ('ticker' if 'ticker' in df.columns else None))
            if col:
                lst = [str(t).strip().upper()
                       for t in df[col].dropna().tolist() if str(t).strip()]
                if lst:
                    return lst
        except Exception:
            continue
    return FALLBACK_TICKERS


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=365):
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
