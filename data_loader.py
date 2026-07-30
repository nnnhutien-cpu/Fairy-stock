import streamlit as st
import pandas as pd
import time
import threading
import requests as _requests
from datetime import datetime, timedelta

# ==========================================================
# IMPORT VNSTOCK (API MỚI)
# ==========================================================
try:
    from vnstock.api.quote import Quote
    from vnstock.api.listing import Listing
    _VNSTOCK_OK = True
except ImportError:
    _VNSTOCK_OK = False

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
# LƯU LỖI ĐỂ DEBUG
# ==========================================================
LAST_ERRORS: dict = {}

def get_last_errors() -> dict:
    return dict(LAST_ERRORS)

# ==========================================================
# NORMALIZE
# ==========================================================
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

# ==========================================================
# YAHOO FINANCE (fallback cho dữ liệu daily)
# ==========================================================
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

# ==========================================================
# FETCH DAILY (dùng cho lịch sử dài hạn)
# ==========================================================
def _fetch(symbol, start, end, interval):
    if not _VNSTOCK_OK:
        if interval == '1D':
            return _fetch_yahoo(symbol, start, end)
        return pd.DataFrame()

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
            LAST_ERRORS[key] = "API trả về DataFrame rỗng."
        except Exception as e:
            LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
            continue

    if interval == '1D':
        return _fetch_yahoo(symbol, start, end)

    return pd.DataFrame()

# ==========================================================
# INTRADAY — CÁC NGUỒN THAY THẾ (không qua vnstock)
# ==========================================================
_INTRADAY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

def _day_timestamps(day_str: str):
    """
    Trả về (t_from, t_to) dạng unix timestamp cho 1 ngày giao dịch.
    Server Streamlit Cloud chạy UTC — phải gắn timezone UTC+7 (Asia/Ho_Chi_Minh)
    rõ ràng, không dùng naive datetime.timestamp() vì sẽ bị lệch 7 tiếng.
    """
    try:
        import pytz
        tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(tz_vn.localize(datetime(dt.year, dt.month, dt.day,  9, 0)).timestamp())
        t_to   = int(tz_vn.localize(datetime(dt.year, dt.month, dt.day, 15, 5)).timestamp())
    except ImportError:
        # Fallback: cộng thủ công 7h = 25200s
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(datetime(dt.year, dt.month, dt.day, 9, 0).timestamp()) - 25200
        t_to   = int(datetime(dt.year, dt.month, dt.day, 15, 5).timestamp()) - 25200
    return t_from, t_to

def _vn_now():
    """Giờ hiện tại theo timezone Việt Nam (UTC+7), dùng để so sánh độ tươi dữ liệu."""
    try:
        import pytz
        tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
        return datetime.now(tz_vn).replace(tzinfo=None)
    except ImportError:
        return datetime.utcnow() + timedelta(hours=7)

def _is_market_hours(now: datetime) -> bool:
    """Có đang trong giờ giao dịch (9:00–15:05, T2–T6) hay không."""
    if now.weekday() >= 5:  # Thứ 7, Chủ nhật
        return False
    t = now.time()
    return (t >= datetime.strptime("09:00", "%H:%M").time()) and \
           (t <= datetime.strptime("15:05", "%H:%M").time())

def _is_fresh(df: pd.DataFrame, max_staleness_minutes: int = 12) -> bool:
    """
    Kiểm tra dữ liệu vừa lấy có đủ mới không (so với giờ VN hiện tại).
    Chỉ áp dụng khi đang trong giờ giao dịch — ngoài giờ, dữ liệu cuối phiên
    là hợp lệ và không nên bị coi là "cũ".
    """
    if df is None or df.empty or 'time' not in df.columns:
        return False
    now = _vn_now()
    if not _is_market_hours(now):
        return True
    last_time = df['time'].max()
    if pd.isna(last_time):
        return False
    return (now - last_time) <= timedelta(minutes=max_staleness_minutes)

def _build_ohlcv_df(t_list, o, h, l, c, v) -> pd.DataFrame:
    """Dựng DataFrame chuẩn từ các list t/o/h/l/c/v (unix timestamp)."""
    times = (
        pd.to_datetime(t_list, unit="s", utc=True)
        .tz_convert("Asia/Ho_Chi_Minh")
        .tz_localize(None)
    )
    df = pd.DataFrame({
        "time":   times,
        "open":   o,
        "high":   h,
        "low":    l,
        "close":  c,
        "volume": v if v else [0] * len(t_list),
    })
    return _normalize(df)

def _fetch_intraday_dnse(day_str: str) -> pd.DataFrame:
    """DNSE / Entrade public chart API — không cần auth."""
    key = f"VNINDEX|1m|DNSE|{day_str}"
    try:
        t_from, t_to = _day_timestamps(day_str)
        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/index"
        params = {
            "symbol": "VNINDEX",
            "resolution": "1",
            "from": t_from,
            "to":   t_to,
        }
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        t_list = data.get("t") or []
        if not t_list:
            LAST_ERRORS[key] = "DNSE trả về rỗng (có thể ngày nghỉ)."
            return pd.DataFrame()
        LAST_ERRORS.pop(key, None)
        return _build_ohlcv_df(
            t_list, data["o"], data["h"], data["l"], data["c"], data.get("v")
        )
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_ssi(day_str: str) -> pd.DataFrame:
    """SSI iBoard public API — thử nhiều endpoint version."""
    key = f"VNINDEX|1m|SSI|{day_str}"
    t_from, t_to = _day_timestamps(day_str)
    endpoints = [
        "https://iboard-query.ssi.com.vn/v2/stock/history",
        "https://iboard-query.ssi.com.vn/v1/stock/chart",
        "https://iboard.ssi.com.vn/dchart/api/history",
    ]
    headers = {
        **_INTRADAY_HEADERS,
        "Referer": "https://iboard.ssi.com.vn/",
        "Origin": "https://iboard.ssi.com.vn",
    }
    params = {"symbol": "VNINDEX", "resolution": "1", "from": t_from, "to": t_to}
    for url in endpoints:
        try:
            r = _requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
            t_list = data.get("t") or []
            if not t_list:
                continue
            LAST_ERRORS.pop(key, None)
            return _build_ohlcv_df(
                t_list, data["o"], data["h"], data["l"], data["c"], data.get("v")
            )
        except Exception:
            continue
    LAST_ERRORS[key] = f"SSI: tất cả endpoints đều fail (404/403/empty) cho {day_str}"
    return pd.DataFrame()


def _fetch_intraday_wifeed(day_str: str) -> pd.DataFrame:
    """Wifeed / Fmarket public API."""
    key = f"VNINDEX|1m|WIFEED|{day_str}"
    try:
        t_from, t_to = _day_timestamps(day_str)
        url = "https://wifeed.vn/api/thong-tin-co-phieu/lich-su-gia-theo-phut"
        params = {
            "symbol": "VNINDEX",
            "from": t_from,
            "to":   t_to,
            "resolution": "1",
        }
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        t_list = data.get("t") or data.get("time") or []
        if not t_list:
            LAST_ERRORS[key] = "Wifeed trả về rỗng."
            return pd.DataFrame()
        LAST_ERRORS.pop(key, None)
        return _build_ohlcv_df(
            t_list,
            data.get("o") or data.get("open", []),
            data.get("h") or data.get("high", []),
            data.get("l") or data.get("low", []),
            data.get("c") or data.get("close", []),
            data.get("v") or data.get("volume"),
        )
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_tcbs(day_str: str) -> pd.DataFrame:
    """TCBS public chart API."""
    key = f"VNINDEX|1m|TCBS|{day_str}"
    try:
        t_from, t_to = _day_timestamps(day_str)
        url = "https://apipubaws.tcbs.com.vn/stock-insight/v1/index/intraday"
        params = {
            "ticker": "VNINDEX",
            "type": "1",
            "from": t_from,
            "to":   t_to,
        }
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") or []
        if not items:
            LAST_ERRORS[key] = "TCBS trả về rỗng."
            return pd.DataFrame()
        df = pd.DataFrame(items)
        rename_map = {
            "tradingDate": "time",
            "closeIndex":  "close",
            "openIndex":   "open",
            "highIndex":   "high",
            "lowIndex":    "low",
            "tradingVolume": "volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        LAST_ERRORS.pop(key, None)
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_vndirect(day_str: str) -> pd.DataFrame:
    """VNDirect market data API."""
    key = f"VNINDEX|1m|VNDIRECT|{day_str}"
    try:
        # VNDirect dùng endpoint khác, lấy theo date string
        url = "https://api.vndirect.com.vn/v4/market-data/index/history"
        params = {
            "code": "VNINDEX",
            "startDate": day_str,
            "endDate": day_str,
            "size": 400,
        }
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") or []
        if not items:
            LAST_ERRORS[key] = "VNDirect trả về rỗng."
            return pd.DataFrame()
        df = pd.DataFrame(items)
        LAST_ERRORS.pop(key, None)
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_vnstock(symbol: str, day_str: str) -> pd.DataFrame:
    """vnstock VCI/MSN — fallback cuối, dễ bị rate limit."""
    if not _VNSTOCK_OK:
        return pd.DataFrame()
    for src in ['VCI', 'MSN']:
        key = f"{symbol}|1m|{src}|{day_str}"
        try:
            _throttle()
            df = Quote(symbol=symbol, source=src).history(
                start=day_str, end=day_str, interval='1m'
            )
            if df is not None and not df.empty:
                LAST_ERRORS.pop(key, None)
                return _normalize(df)
            LAST_ERRORS[key] = "vnstock trả về rỗng."
        except Exception as e:
            LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
            continue
    return pd.DataFrame()

def _fetch_intraday_day(symbol: str, day_str: str, require_fresh: bool = False) -> pd.DataFrame:
    """
    Lấy dữ liệu 1 phút cho 1 ngày.
    Thứ tự ưu tiên: DNSE → SSI → Wifeed → TCBS → VNDirect → vnstock (VCI/MSN)

    Nếu require_fresh=True (dùng cho NGÀY HÔM NAY trong giờ giao dịch):
    không chấp nhận ngay kết quả đầu tiên "không rỗng" — mà còn kiểm tra
    dữ liệu đó có đủ MỚI hay không (timestamp cuối cùng cách hiện tại
    không quá ~12 phút). Nếu nguồn đầu trả về bản cache/kẹt cũ, hệ thống
    sẽ tự động thử các nguồn tiếp theo thay vì dừng lại ở dữ liệu cũ.
    Nếu không có nguồn nào tươi, vẫn trả về bản mới nhất (gần đây nhất)
    thu được, thay vì bỏ trắng hoàn toàn.
    """
    fetchers = [
        _fetch_intraday_dnse,
        _fetch_intraday_ssi,
        _fetch_intraday_wifeed,
        _fetch_intraday_tcbs,
        _fetch_intraday_vndirect,
    ]

    best_df = pd.DataFrame()
    best_last_time = None

    if symbol == "VNINDEX":
        for fetcher in fetchers:
            df = fetcher(day_str)
            if df.empty:
                continue

            if not require_fresh or _is_fresh(df):
                return df

            # Dữ liệu không rỗng nhưng bị coi là "cũ" — giữ lại làm phương án
            # dự phòng, đồng thời thử tiếp nguồn khác để tìm bản mới hơn.
            last_time = df['time'].max()
            if best_last_time is None or (pd.notna(last_time) and last_time > best_last_time):
                best_df = df
                best_last_time = last_time

        if not best_df.empty:
            LAST_ERRORS[f"VNINDEX|1m|freshness|{day_str}"] = (
                f"Không có nguồn nào trả dữ liệu đủ mới — dùng bản gần nhất "
                f"(cập nhật lúc {best_last_time})."
            )
            return best_df

    # Fallback cuối: vnstock
    return _fetch_intraday_vnstock(symbol, day_str)

# ==========================================================
# PUBLIC API
# ==========================================================
@st.cache_data(ttl=86400)
def get_all_tickers(exchange='all'):
    if not _VNSTOCK_OK:
        return FALLBACK_TICKERS

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

    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch(ticker, start_date, end_date, '1D')

@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=365):
    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch('VNINDEX', start_date, end_date, '1D')

@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex():
    """
    Lấy dữ liệu intraday VNINDEX 1 phút.
    Thử tối đa 6 ngày gần nhất, thu đủ 2 phiên có dữ liệu thì dừng.
    Thứ tự nguồn: DNSE → SSI → Wifeed → TCBS → VNDirect → vnstock

    Ngày HÔM NAY (offset=0) bắt buộc kiểm tra độ tươi (require_fresh=True)
    để tránh bị "kẹt" ở dữ liệu cache cũ từ một nguồn duy nhất — đây là lý
    do trước đây phải bấm "Cập nhật" nhiều lần mới ra đúng giờ hiện tại.
    """
    frames = []
    for offset in range(6):
        day = (datetime.now() - timedelta(days=offset)).strftime('%Y-%m-%d')
        df_day = _fetch_intraday_day('VNINDEX', day, require_fresh=(offset == 0))
        if not df_day.empty:
            frames.append(df_day)
        if len(frames) >= 2:
            break

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result = result.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return result
