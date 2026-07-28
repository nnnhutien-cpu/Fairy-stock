import streamlit as st
import pandas as pd
import time
import threading
from datetime import datetime, timedelta
from vnstock.api.quote import Quote
from vnstock.api.listing import Listing

# ==========================================================
# CACHE DÀI HẠN TỪ SUPABASE (DO BOT NỀN BƠM SẴN 1 LẦN/NGÀY)
# ==========================================================
_supabase_client = None
_supabase_tried = False

def _get_supabase():
    global _supabase_client, _supabase_tried
    if _supabase_tried:
        return _supabase_client
    _supabase_tried = True
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        _supabase_client = create_client(url, key)
    except Exception:
        _supabase_client = None
    return _supabase_client

def _read_from_cache(ticker, days_back, max_staleness_days=4):
    """Đọc lịch sử giá từ Supabase nếu có và đủ mới. Trả về None nếu không có/quá cũ -> gọi API sống."""
    sb = _get_supabase()
    if sb is None:
        return None
    try:
        resp = (
            sb.table("stock_prices")
            .select("date,open,high,low,close,volume")
            .eq("ticker", ticker)
            .order("date", desc=True)
            .limit(int(days_back * 1.6) + 10)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None

        newest_date = pd.to_datetime(rows[0]["date"])
        if (datetime.now() - newest_date).days > max_staleness_days:
            return None

        df = pd.DataFrame(rows)
        df = df.rename(columns={"date": "time"})
        return _normalize(df)
    except Exception:
        return None

# ==========================================================
# TỰ GIỚI HẠN TỐC ĐỘ GỌI API
# ==========================================================
_rate_lock = threading.Lock()
_call_timestamps = []
_rate_limit_per_min = 18

def set_rate_limit(requests_per_minute: int):
    global _rate_limit_per_min
    _rate_limit_per_min = max(1, int(requests_per_minute))

def _throttle():
    with _rate_lock:
        now = time.time()
        while _call_timestamps and now - _call_timestamps[0] > 60:
            _call_timestamps.pop(0)
        if len(_call_timestamps) >= _rate_limit_per_min:
            wait = 60 - (now - _call_timestamps[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _call_timestamps and now - _call_timestamps[0] > 60:
                _call_timestamps.pop(0)
        _call_timestamps.append(now)

FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

# ==========================================================
# CHẨN ĐOÁN LỖI (MỚI): thay vì "except Exception: continue" âm thầm,
# lưu lại lỗi thật gần nhất để app.py / bạn có thể hiển thị ra và biết
# CHÍNH XÁC vì sao 1 nguồn dữ liệu bị fail, thay vì chỉ thấy "đang chờ dữ liệu".
# ==========================================================
LAST_ERRORS = {}  # { "VNINDEX|1m|VCI": "thông báo lỗi..." }

def get_last_errors() -> dict:
    """Gọi hàm này từ app.py để hiển thị lý do fail thật gần nhất (debug)."""
    return dict(LAST_ERRORS)

def _normalize(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    if 'date' in df.columns and 'time' not in df.columns:
        df.rename(columns={'date': 'time'}, inplace=True)

    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
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
        yf_symbol = "^VNINDEX" if symbol == "VNINDEX" else f"{symbol}.VN"

        df = yf.download(yf_symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.columns = [str(c).lower().strip() for c in df.columns]

        if 'date' in df.columns:
            df.rename(columns={'date': 'time'}, inplace=True)

        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[f"{symbol}|yahoo"] = str(e)
        return pd.DataFrame()

def _fetch(symbol, start, end, interval):
    """Lấy dữ liệu OHLC theo NGÀY (1D/1W/1M). Dùng cho lịch sử dài hạn, KHÔNG dùng cho dữ liệu phút
    (xem _fetch_intraday_day bên dưới — vnstock chỉ hỗ trợ lấy intraday theo từng ngày một)."""
    sources = ['VCI', 'MSN']

    for src in sources:
        key = f"{symbol}|{interval}|{src}"
        try:
            _throttle()
            df = Quote(symbol=symbol, source=src).history(
                start=start, end=end, interval=interval
            )
            if df is not None and not df.empty:
                LAST_ERRORS.pop(key, None)
                return _normalize(df)
            LAST_ERRORS[key] = "API trả về DataFrame rỗng (không lỗi, nhưng không có dữ liệu)."
        except Exception as e:
            LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
            continue

    if interval == '1D':
        return _fetch_yahoo(symbol, start, end)

    return pd.DataFrame()

# data_loader.py — thay hàm _fetch_intraday_day và get_intraday_vnindex

import requests as _requests

def _fetch_intraday_dnse(day_str: str) -> pd.DataFrame:
    """DNSE entrade API — public, không cần auth."""
    try:
        from datetime import datetime
        import time as _time
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(datetime(dt.year, dt.month, dt.day, 9, 0).timestamp())
        t_to   = int(datetime(dt.year, dt.month, dt.day, 15, 1).timestamp())
        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/index"
        params = {"symbol": "VNINDEX", "resolution": "1", "from": t_from, "to": t_to}
        r = _requests.get(url, params=params,
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data.get("t"):
            return pd.DataFrame()
        df = pd.DataFrame({
            "time":   pd.to_datetime(data["t"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None),
            "open":   data["o"],
            "high":   data["h"],
            "low":    data["l"],
            "close":  data["c"],
            "volume": data.get("v", [0] * len(data["t"])),
        })
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[f"VNINDEX|1m|DNSE|{day_str}"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


def _fetch_intraday_ssi(day_str: str) -> pd.DataFrame:
    """SSI iBoard public API."""
    try:
        from datetime import datetime
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(datetime(dt.year, dt.month, dt.day, 9, 0).timestamp())
        t_to   = int(datetime(dt.year, dt.month, dt.day, 15, 1).timestamp())
        url = "https://iboard-query.ssi.com.vn/v2/stock/history"
        params = {"symbol": "VNINDEX", "resolution": "1", "from": t_from, "to": t_to}
        r = _requests.get(url, params=params,
                          headers={"User-Agent": "Mozilla/5.0",
                                   "Referer": "https://iboard.ssi.com.vn/"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        # SSI trả về {"t": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...]}
        t_list = data.get("t") or []
        if not t_list:
            return pd.DataFrame()
        df = pd.DataFrame({
            "time":   pd.to_datetime(t_list, unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None),
            "open":   data["o"],
            "high":   data["h"],
            "low":    data["l"],
            "close":  data["c"],
            "volume": data.get("v", [0] * len(t_list)),
        })
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[f"VNINDEX|1m|SSI|{day_str}"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


def _fetch_intraday_tcbs(day_str: str) -> pd.DataFrame:
    """TCBS public API."""
    try:
        from datetime import datetime
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(datetime(dt.year, dt.month, dt.day, 9, 0).timestamp())
        t_to   = int(datetime(dt.year, dt.month, dt.day, 15, 1).timestamp())
        url = "https://apipubaws.tcbs.com.vn/stock-insight/v1/index/intraday"
        params = {"ticker": "VNINDEX", "type": "1", "from": t_from, "to": t_to}
        r = _requests.get(url, params=params,
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") or []
        if not items:
            return pd.DataFrame()
        df = pd.DataFrame(items)
        df = df.rename(columns={"tradingDate": "time", "closeIndex": "close",
                                 "openIndex": "open", "highIndex": "high",
                                 "lowIndex": "low", "tradingVolume": "volume"})
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[f"VNINDEX|1m|TCBS|{day_str}"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


def _fetch_intraday_day(symbol, day_str):
    """
    Thử theo thứ tự: DNSE → SSI → TCBS → vnstock VCI → vnstock MSN
    Các nguồn đầu không qua vnstock nên không bị rate limit.
    """
    # --- Nguồn 1: DNSE (nhanh nhất, ít bị chặn nhất) ---
    if symbol == "VNINDEX":
        df = _fetch_intraday_dnse(day_str)
        if not df.empty:
            return df

        # --- Nguồn 2: SSI ---
        df = _fetch_intraday_ssi(day_str)
        if not df.empty:
            return df

        # --- Nguồn 3: TCBS ---
        df = _fetch_intraday_tcbs(day_str)
        if not df.empty:
            return df

    # --- Nguồn 4 & 5: vnstock (fallback cuối, dễ bị rate limit) ---
    sources = ['VCI', 'MSN']
    for src in sources:
        key = f"{symbol}|1m|{src}|{day_str}"
        try:
            _throttle()
            df = Quote(symbol=symbol, source=src).history(
                start=day_str, end=day_str, interval='1m'
            )
            if df is not None and not df.empty:
                LAST_ERRORS.pop(key, None)
                return _normalize(df)
            LAST_ERRORS[key] = "API trả về rỗng."
        except Exception as e:
            LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
            continue

    return pd.DataFrame()
