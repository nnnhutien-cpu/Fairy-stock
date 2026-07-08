import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from vnstock import Vnstock

FALLBACK_TICKERS = [
    # HOSE lớn
    "HPG","SSI","VND","FPT","TCB","MBB","MWG","VIC","VHM","VNM","VCB","CTG","BID",
    "GAS","MSN","VRE","PLX","POW","STB","VPB","ACB","HDB","TPB","SHB","VJC","GVR",
    "DGC","DIG","DXG","PDR","NVL","KDH","REE","GEX","VCI","HCM","VIX","DCM","DPM",
    "PVD","PVT","BVH","SAB","PNJ","MSB","OCB","EIB","LPB","SSB","BCM","KBC","NLG",
    # HNX
    "SHS","PVS","CEO","IDC","VCS","MBS","TNG","HUT","BVS","TAR","L14","NVB","VGS",
    # UPCOM
    "BSR","VGI","MML","ACV","VEA","QNS","MCH","VTP","FOX","OIL","BVB","ABB","LTG",
]

VN_SOURCES = ['VCI', 'KBS', 'FMP']  # nguồn hợp lệ vnstock 4.0
TCBS_BARS = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _normalize(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    for k in ['tradingdate', 'date']:
        if k in df.columns and 'time' not in df.columns:
            df.rename(columns={k: 'time'}, inplace=True)
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'time' in df.columns:
        df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return df


def _tcbs_direct(symbol, days_back, asset_type='stock', resolution='D'):
    """Gọi thẳng API public TCBS (endpoint khác VCI, ít bị chặn hơn)."""
    try:
        params = {
            "ticker": symbol,
            "type": asset_type,
            "resolution": resolution,
            "to": int(datetime.now().timestamp()),
            "countBack": min(days_back, 2000),
        }
        r = requests.get(TCBS_BARS, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return _normalize(pd.DataFrame(data))
    except Exception:
        pass
    return pd.DataFrame()


def _vnstock(symbol, start, end, interval):
    for src in VN_SOURCES:
        try:
            df = Vnstock().stock(symbol=symbol, source=src).quote.history(
                start=start, end=end, interval=interval)
            if df is not None and len(df) > 0:
                return _normalize(df)
        except Exception:
            continue
    return pd.DataFrame()


@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    # Thử lấy danh sách qua vnstock (endpoint listing có thể không bị chặn)
    for src in VN_SOURCES:
        try:
            df = Vnstock().stock(symbol='ACB', source=src).listing.symbols_by_exchange()
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'type' in df.columns:
                df = df[df['type'].astype(str).str.upper() == 'STOCK']
            if 'exchange' in df.columns:
                df = df[df['exchange'].astype(str).str.upper().isin(['HOSE','HSX','HNX','UPCOM'])]
                if exchange != 'all':
                    tgt = ['HOSE','HSX'] if str(exchange).upper() in ('HOSE','HSX') else [str(exchange).upper()]
                    df = df[df['exchange'].astype(str).str.upper().isin(tgt)]
            col = 'symbol' if 'symbol' in df.columns else ('ticker' if 'ticker' in df.columns else None)
            if col:
                lst = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
                if lst:
                    return lst
        except Exception:
            continue
    return FALLBACK_TICKERS  # danh sách dự phòng khi listing bị chặn


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=3650):
    df = _tcbs_direct(ticker, days_back, 'stock')     # 1) TCBS trực tiếp
    if not df.empty:
        return df
    end_date = datetime.now().strftime('%Y-%m-%d')     # 2) fallback vnstock
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _vnstock(ticker, start_date, end_date, '1D')


@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=3650):
    df = _tcbs_direct('VNINDEX', days_back, 'index')
    if not df.empty:
        return df
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _vnstock('VNINDEX', start_date, end_date, '1D')


@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    df = _tcbs_direct('VNINDEX', 5, 'index', resolution='1')   # nến 1 phút
    if not df.empty:
        return df
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    return _vnstock('VNINDEX', start_date, end_date, '1m')
