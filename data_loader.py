import streamlit as st
import pandas as pd
import requests
import time
import threading
from datetime import datetime, timedelta, timezone

# ==========================================================
# THỨ TỰ NGUỒN DỮ LIỆU GIÁ
#   1. Cache Supabase (bot nền bulk_fetch_prices.py bơm sẵn 1 lần/ngày)  -> tức thì
#   2. TCBS (API công khai)                                               -> nguồn chính
#   3. Yahoo Finance                                                      -> dự phòng
# vnstock KHÔNG còn dùng cho giá. Chỉ còn dùng (tuỳ chọn) để lấy danh sách mã theo sàn;
# nếu không import được vnstock thì tự rơi về danh sách mã trong Supabase.
# ==========================================================

TCBS_BARS_URL = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
_TCBS_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
INDEX_SYMBOLS = {"VNINDEX", "HNXINDEX", "UPCOMINDEX", "VN30", "HNX30"}
TCBS_MAX_PER_MIN = 100  # trần an toàn cho API công khai TCBS (khớp TCBS_RATE_LIMIT của bot nền)
_VN_TZ = timezone(timedelta(hours=7))

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
            .limit(int(days_back * 1.6) + 10)  # dư ra để bù ngày nghỉ/lễ
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        newest_date = pd.to_datetime(rows[0]["date"])
        if (datetime.now() - newest_date).days > max_staleness_days:
            return None  # cache quá cũ (bot nền có thể đã ngừng chạy) -> gọi API sống cho chắc
        df = pd.DataFrame(rows)
        df = df.rename(columns={"date": "time"})
        return _scale_price_unit(_normalize(df), ticker)
    except Exception:
        return None  # bảng chưa tồn tại / lỗi kết nối -> im lặng rơi về API sống


# ==========================================================
# TỰ GIỚI HẠN TỐC ĐỘ GỌI API
# ==========================================================
_rate_lock = threading.Lock()
_call_timestamps = []
_rate_limit_per_min = 18


def set_rate_limit(requests_per_minute: int):
    """Main.py gọi hàm này để chỉnh tốc độ. Với TCBS luôn bị chặn trần ở TCBS_MAX_PER_MIN."""
    global _rate_limit_per_min
    _rate_limit_per_min = max(1, int(requests_per_minute))


def _throttle():
    limit = min(_rate_limit_per_min, TCBS_MAX_PER_MIN)
    with _rate_lock:
        now = time.time()
        while _call_timestamps and now - _call_timestamps[0] > 60:
            _call_timestamps.pop(0)
        if len(_call_timestamps) >= limit:
            wait = 60 - (now - _call_timestamps[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _call_timestamps and now - _call_timestamps[0] > 60:
                _call_timestamps.pop(0)
        _call_timestamps.append(now)


# Danh sách dự phòng nếu không lấy được danh sách mã từ bất kỳ nguồn nào
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
        # Xóa timezone (tz-naive) để không crash khi trừ ngày tháng ở main.py
        if getattr(df['time'].dt, 'tz', None) is not None:
            df['time'] = df['time'].dt.tz_localize(None)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'time' in df.columns:
        df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return df


def _scale_price_unit(df, symbol):
    """Đưa giá cổ phiếu về đơn vị 'nghìn đồng' (25.5) như hệ thống đang dùng.
    TCBS/Yahoo trả theo đồng (25500). Cổ phiếu VN không có giá > 1.000 nghìn đồng nên
    median close > 1000 chắc chắn là đơn vị đồng. Chỉ số (VNINDEX...) giữ nguyên."""
    if df is None or df.empty or 'close' not in df.columns:
        return df
    if str(symbol).upper() in INDEX_SYMBOLS:
        return df
    med = df['close'].dropna().median()
    if pd.notna(med) and med > 1000:
        df = df.copy()
        for c in ['open', 'high', 'low', 'close']:
            if c in df.columns:
                df[c] = df[c] / 1000.0
    return df


# ==========================================================
# NGUỒN 1: TCBS
# ==========================================================
def _fetch_tcbs(symbol, start, end, interval):
    sym = str(symbol).upper()
    is_index = sym in INDEX_SYMBOLS
    daily = (interval == '1D')

    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    to_ts = min(int(time.time()), int((end_ts + pd.Timedelta(days=1)).timestamp()))
    count_back = max(10, (end_ts - start_ts).days + 5) if daily else 1500

    params = {
        "ticker": sym,
        "type": "index" if is_index else "stock",
        "resolution": "D" if daily else "1",
        "to": to_ts,
        "countBack": count_back,
    }

    _throttle()
    r = None
    for attempt in (1, 2):
        r = requests.get(TCBS_BARS_URL, params=params, headers=_TCBS_HEADERS, timeout=10)
        if r.status_code == 429 and attempt == 1:
            time.sleep(2)  # bị giới hạn tốc độ -> chờ rồi thử lại 1 lần
            continue
        break
    r.raise_for_status()

    rows = (r.json() or {}).get("data") or []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.rename(columns={"tradingdate": "time"})
    if "time" not in df.columns or "close" not in df.columns:
        return pd.DataFrame()

    t = pd.to_datetime(df["time"], errors="coerce")
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)  # đổi sang giờ VN rồi bỏ tz
    if daily:
        t = t.dt.normalize()
    df["time"] = t

    keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
    df = _normalize(df[keep])
    if df.empty:
        return df
    if daily:
        df = df[df["time"] >= start_ts].reset_index(drop=True)
    df = _scale_price_unit(df, sym)
    df.attrs["source"] = "TCBS"
    return df


# ==========================================================
# NGUỒN 2 (DỰ PHÒNG): YAHOO FINANCE
# ==========================================================
def _fetch_yahoo(symbol, start, end, interval='1D'):
    try:
        import yfinance as yf
        # VNINDEX trên Yahoo tên là ^VNINDEX; cổ phiếu là <MÃ>.VN
        sym = str(symbol).upper()
        yf_symbol = "^VNINDEX" if sym == "VNINDEX" else f"{sym}.VN"
        if interval == '1D':
            df = yf.download(yf_symbol, start=start, end=end, progress=False, auto_adjust=True)
        else:
            df = yf.download(yf_symbol, period="5d", interval="1m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        # Xử lý Multi-Index cột của yfinance bản mới
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.columns = [str(c).lower().strip() for c in df.columns]
        if 'date' in df.columns:
            df.rename(columns={'date': 'time'}, inplace=True)
        elif 'datetime' in df.columns:
            df.rename(columns={'datetime': 'time'}, inplace=True)
        df = _normalize(df)
        if df.empty:
            return df
        if interval == '1D':
            df['time'] = df['time'].dt.normalize()
        df = _scale_price_unit(df, sym)
        df.attrs["source"] = "Yahoo"
        return df
    except Exception:
        return pd.DataFrame()


def _fetch(symbol, start, end, interval):
    # 1. TCBS (nguồn chính)
    try:
        df = _fetch_tcbs(symbol, start, end, interval)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass  # TCBS lỗi/bị chặn IP/hết hạn mức -> chuyển sang Yahoo
    # 2. Yahoo Finance (dự phòng)
    return _fetch_yahoo(symbol, start, end, interval)


# ==========================================================
# DANH SÁCH MÃ
# ==========================================================
def _listing_from_vnstock(exchange):
    """TUỲ CHỌN: lấy danh sách mã theo sàn bằng vnstock nếu cài được. Không có thì trả []."""
    try:
        from vnstock.api.listing import Listing
    except Exception:
        return []
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
        except Exception:
            continue
    return []


def _listing_from_supabase():
    """Danh sách mã có dữ liệu trong ngày gần nhất của bảng stock_prices (KHÔNG lọc được theo sàn)."""
    sb = _get_supabase()
    if sb is None:
        return []
    try:
        top = sb.table("stock_prices").select("date").order("date", desc=True).limit(1).execute().data
        if not top:
            return []
        latest = top[0]["date"]
        tickers, offset = [], 0
        while True:
            rows = (
                sb.table("stock_prices").select("ticker").eq("date", latest)
                .range(offset, offset + 999).execute().data or []
            )
            tickers += [r["ticker"] for r in rows]
            if len(rows) < 1000:
                break
            offset += 1000
        out = {str(t).strip().upper() for t in tickers if t}
        return sorted(t for t in out if len(t) == 3 and t.isalnum())  # chỉ lấy mã cổ phiếu 3 ký tự
    except Exception:
        return []


@st.cache_data(ttl=86400)  # Lưu cache danh sách mã trong 24h
def get_all_tickers(exchange='all'):
    lst = _listing_from_vnstock(exchange) or _listing_from_supabase()
    return lst if lst else FALLBACK_TICKERS


# ==========================================================
# HÀM CÔNG KHAI (GIỮ NGUYÊN TÊN & CHỮ KÝ ĐỂ main.py KHÔNG PHẢI SỬA)
# ==========================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(ticker, days_back=200):
    # 1. Ưu tiên cache Supabase -> TỨC THÌ, không tốn quota API.
    cached = _read_from_cache(ticker, days_back)
    if cached is not None and len(cached) >= min(60, days_back // 2):
        return cached

    # 2. Không có cache / cache quá cũ -> TCBS, lỗi thì Yahoo.
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
    if df is not None and not df.empty:
        return df
    return pd.DataFrame()


def get_expected_latest_trading_date():
    """Ngày giao dịch gần nhất mà dữ liệu EOD đáng lẽ phải có (giờ VN, chưa tính ngày lễ).
    Sau 15:00 ngày thường -> hôm nay; trước 15:00 hoặc cuối tuần -> phiên trước đó."""
    now = datetime.now(_VN_TZ)
    d = now.date()
    if d.weekday() < 5 and now.hour >= 15:
        return d
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
