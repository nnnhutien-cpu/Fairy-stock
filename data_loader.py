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

def _fetch_intraday_day(symbol, day_str):
    """
    Lấy dữ liệu 1 phút cho ĐÚNG 1 NGÀY (start=end=day_str).
    LƯU Ý QUAN TRỌNG: dữ liệu intraday theo phút của vnstock chỉ được hỗ trợ
    lấy theo TỪNG PHIÊN GIAO DỊCH (1 ngày), KHÔNG lấy nguyên 1 khoảng nhiều
    ngày cùng lúc như dữ liệu daily -> đây là lý do bản cũ (xin 5 ngày cùng
    lúc với interval='1m') hay bị trả về rỗng/lỗi im lặng.
    """
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
            LAST_ERRORS[key] = "API trả về DataFrame rỗng cho ngày này (có thể ngày nghỉ / chưa vào phiên)."
        except Exception as e:
            LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    for src in ['vci', 'kbs']:
        try:
            _throttle()
            df = Listing(source=src).symbols_by_exchange()
            df.columns = [str(c).lower().strip() for c in df.columns]

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
        except Exception as e:
            LAST_ERRORS[f"get_all_tickers|{src}"] = f"{type(e).__name__}: {e}"
            continue

    return FALLBACK_TICKERS

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=200):
    cached = _read_from_cache(ticker, days_back)
    if cached is not None and len(cached) >= min(60, days_back // 2):
        return cached

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
    """
    SỬA: thay vì xin nguyên 1 khoảng 5 ngày với interval='1m' (dễ bị API từ
    chối/âm thầm trả rỗng), giờ lấy TỪNG NGÀY một (đúng cách vnstock hỗ trợ
    intraday) rồi ghép lại — đủ cho 2 phiên gần nhất (hôm nay + hôm qua) mà
    app.py cần để so sánh thanh khoản.
    """
    frames = []
    # thử tối đa 6 ngày gần nhất để chắc chắn vớt được >= 2 phiên có giao dịch
    # (bỏ qua T7/CN và ngày lễ không có dữ liệu)
    for offset in range(6):
        day = (datetime.now() - timedelta(days=offset)).strftime('%Y-%m-%d')
        df_day = _fetch_intraday_day('VNINDEX', day)
        if not df_day.empty:
            frames.append(df_day)
        # đã đủ 2 phiên có dữ liệu thì dừng sớm, đỡ tốn request
        if len(frames) >= 2:
            break

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result = result.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return result
