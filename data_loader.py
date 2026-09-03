import streamlit as st
import pandas as pd
import time
import threading
import concurrent.futures
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
    
def _fetch_dnse(symbol, days_back=350):
    """DNSE Chart API — public, không cần auth, thêm vào trước Yahoo."""
    import requests
    from datetime import datetime, timedelta
    end_ts   = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days_back)).timestamp())
    try:
        resp = requests.get(
            "https://services.entrade.com.vn/chart/history",
            params={"symbol": symbol.upper(), "resolution": "D",
                    "from": start_ts, "to": end_ts},
            timeout=10
        )
        data = resp.json()
        if data.get("s") != "ok" or not data.get("t"):
            return pd.DataFrame()
        df = pd.DataFrame({
            "time":   pd.to_datetime(data["t"], unit="s"),
            "open":   data["o"], "high": data["h"],
            "low":    data["l"], "close": data["c"],
            "volume": data["v"],
        })
        return _normalize(df.sort_values("time").reset_index(drop=True))
    except Exception:
        return pd.DataFrame()
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

def get_expected_latest_trading_date(now: datetime = None):
    """
    Trả về ngày giao dịch GẦN NHẤT mà dữ liệu đóng cửa lẽ ra phải sẵn sàng,
    dựa trên quy tắc thực tế: phiên đóng cửa lúc 15h00, dữ liệu (từ nguồn
    ngoài / bot cào) được cập nhật xong chậm nhất lúc 17h00 (giờ VN, UTC+7).
    """
    if now is None:
        now = _vn_now()
    d = now.date()
    if now.weekday() < 5 and now.time() < datetime.strptime("17:00", "%H:%M").time():
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def get_data_freshness(df, now: datetime = None):
    """
    So sánh ngày dữ liệu MỚI NHẤT trong df với ngày giao dịch kỳ vọng.
    """
    expected_date = get_expected_latest_trading_date(now)
    if df is None or df.empty or "time" not in df.columns:
        return {"latest_date": None, "expected_date": expected_date, "lag_days": None, "is_stale": True}
    latest_date = pd.to_datetime(df["time"].max()).date()
    lag_days = (expected_date - latest_date).days
    return {
        "latest_date": latest_date,
        "expected_date": expected_date,
        "lag_days": lag_days,
        "is_stale": lag_days > 0,
    }


def _read_from_cache(ticker, days_back):
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
        # ĐÃ SỬA: không còn gate theo "newest_date >= expected_date".
        # Trước đây hễ Supabase trễ dù chỉ 1 phiên (bot chạy chậm/lỗi) là toàn bộ
        # request rơi xuống _fetch() sống (vnstock VCI→MSN→Yahoo, có thể mất
        # vài giây tới cả phút nếu dính _throttle) -> "tải mã" bị chậm hẳn.
        # Giờ luôn trả cache Supabase ngay lập tức (banner độ trễ + nút "Làm mới"
        # ở UI đã lo phần cảnh báo/refresh chủ động), giữ load mã ổn định <1s.
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
    """
    ĐÃ SỬA: KHÔNG còn time.sleep() bên trong `with _rate_lock`.
    Trước đây, hễ 1 trong N luồng chạm rate limit là nó ngủ (tới ~60s)
    trong khi vẫn giữ lock -> toàn bộ các luồng khác (đang chờ acquire
    lock để tự kiểm tra quota của MÌNH) bị đứng khựng theo, biến
    ThreadPoolExecutor(15 luồng) thành chạy gần như tuần tự với các
    khoảng nghỉ dài. Đây là nguyên nhân chính khiến quét ~58 mã mất
    10-20 phút thay vì vài chục giây.
    Giờ mỗi luồng chỉ giữ lock trong lúc đọc/cập nhật danh sách
    timestamp (rất nhanh), rồi NGỦ Ở NGOÀI lock -> các luồng khác vẫn
    tự do kiểm tra & tiến hành ngay khi còn quota.
    """
    while True:
        with _rate_lock:
            now = time.time()
            while _call_timestamps and now - _call_timestamps[0] > 60:
                _call_timestamps.pop(0)
            if len(_call_timestamps) < _rate_limit_per_min:
                _call_timestamps.append(now)
                return
            wait = 60 - (now - _call_timestamps[0]) + 0.05
        time.sleep(max(wait, 0.05))

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
    """Fallback cuối cùng: lấy dữ liệu daily từ Yahoo Finance (mã.VN)."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        ticker = f"{symbol}.VN"
        df = yf.Ticker(ticker).history(start=start, end=end)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df.columns = [str(c).lower().strip() for c in df.columns]
        for col in list(df.columns):
            if 'date' in col:
                df.rename(columns={col: 'time'}, inplace=True)
                break
        return _normalize(df)
    except Exception:
        return pd.DataFrame()

# ==========================================================
# CHẠY 1 LỆNH GỌI API VỚI TIMEOUT CỨNG
# ==========================================================
def _run_with_timeout(fn, timeout=8):
    """
    Bọc 1 lệnh gọi mạng (vd Quote(...).history(...)) với giới hạn thời
    gian cứng. Trước đây nếu VCI/MSN bị treo (mạng chậm/API không phản
    hồi), luồng xử lý mã đó có thể "đứng hình" rất lâu (không có timeout
    nào chặn), chiếm mất 1 trong số luồng worker và kéo dài tổng thời
    gian quét. Giờ tối đa `timeout` giây là buộc phải trả về None để
    rơi xuống nguồn dự phòng tiếp theo (MSN -> DNSE -> Yahoo).
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None
        except Exception:
            raise
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

def _race(tasks: dict, timeout: float = 6):
    """
    ĐUA nhiều nguồn dữ liệu (vd VCI, MSN, DNSE) CÙNG LÚC thay vì thử
    tuần tự từng nguồn một. Trước đây: VCI timeout 8s -> rồi mới thử
    MSN timeout 8s -> rồi mới thử DNSE... cộng dồn có thể trên 15-20s
    CHO 1 MÃ. Giờ cả 3 nguồn được bắn đi đồng thời, hàm trả về ngay khi
    có nguồn xong (theo thứ tự hoàn thành), tổng cộng không quá
    `timeout` giây thay vì cộng dồn timeout từng nguồn.

    tasks: {"TÊN_NGUỒN": hàm_không_tham_số}
    Trả về: list [(tên_nguồn, kết_quả_hoặc_Exception), ...] theo thứ tự
    hoàn thành trước; nguồn nào chưa xong khi hết giờ sẽ bị bỏ qua luôn
    (không chờ thêm).
    """
    if not tasks:
        return []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks))
    out = []
    try:
        future_map = {ex.submit(fn): name for name, fn in tasks.items()}
        pending = set(future_map.keys())
        deadline = time.time() + timeout
        while pending:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            done, pending = concurrent.futures.wait(
                pending, timeout=remaining,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for fut in done:
                name = future_map[fut]
                try:
                    out.append((name, fut.result()))
                except Exception as e:
                    out.append((name, e))
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out

# ==========================================================
# FETCH DAILY (dùng cho lịch sử dài hạn)
# ĐÃ SỬA (v2 - đua song song): trước đây thử tuần tự VCI -> MSN ->
# DNSE -> Yahoo, mỗi nguồn timeout riêng cộng dồn lại có thể trên
# 15-20s CHO 1 MÃ nếu nguồn đầu không phản hồi nhanh. Giờ VCI, MSN,
# DNSE được bắn đi ĐỒNG THỜI (xem hàm _race), dùng kết quả hợp lệ về
# sớm nhất; chỉ khi CẢ 3 đều thất bại mới thử Yahoo (nguồn chậm/kém
# ổn định nhất, để cuối). Tổng thời gian chờ tối đa cho 1 mã giảm từ
# ~16-20s xuống còn ~6-11s.
# ==========================================================
def _fetch(symbol, start, end, interval):
    if not _VNSTOCK_OK:
        if interval == '1D':
            return _fetch_yahoo(symbol, start, end)
        return pd.DataFrame()

    expected_date = get_expected_latest_trading_date() if interval == '1D' else None
    best_df = pd.DataFrame()
    best_last_date = None

    def _last_date(d):
        if d is None or d.empty or 'time' not in d.columns:
            return None
        v = pd.to_datetime(d['time'].max())
        return v.date() if pd.notna(v) else None

    def _call_vci():
        _throttle()
        return Quote(symbol=symbol, source='VCI').history(start=start, end=end, interval=interval)

    def _call_msn():
        _throttle()
        return Quote(symbol=symbol, source='MSN').history(start=start, end=end, interval=interval)

    tasks = {'VCI': _call_vci, 'MSN': _call_msn}
    if interval == '1D':
        days = (datetime.strptime(end, '%Y-%m-%d') -
                datetime.strptime(start, '%Y-%m-%d')).days + 10
        tasks['DNSE'] = lambda: _fetch_dnse(symbol, days_back=days)

    for src, result in _race(tasks, timeout=6):
        key = f"{symbol}|{interval}|{src}"
        if isinstance(result, Exception):
            LAST_ERRORS[key] = f"{type(result).__name__}: {result}"
            continue
        df = result
        if df is None or df.empty:
            LAST_ERRORS[key] = "API trả về DataFrame rỗng."
            continue
        LAST_ERRORS.pop(key, None)
        df = _normalize(df)
        ld = _last_date(df)
        if interval != '1D' or expected_date is None or (ld is not None and ld >= expected_date):
            return df
        if best_last_date is None or (ld is not None and ld > best_last_date):
            best_df, best_last_date = df, ld
        LAST_ERRORS[key] = f"{src} chỉ có dữ liệu tới {ld} (kỳ vọng {expected_date})."

    if not best_df.empty:
        return best_df

    if interval == '1D':
        # Yahoo là nguồn dự phòng cuối cùng — kém ổn định nhất với mã VN
        # nên chỉ thử KHI cả VCI/MSN/DNSE đều thất bại, và vẫn có timeout
        # cứng để không treo luồng.
        df_yahoo = _run_with_timeout(lambda: _fetch_yahoo(symbol, start, end), timeout=5)
        if df_yahoo is not None and not df_yahoo.empty:
            return _normalize(df_yahoo)

    return best_df

# ==========================================================
# INTRADAY — CÁC NGUỒN THAY THẾ (không qua vnstock)
# ==========================================================
_INTRADAY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

def _day_timestamps(day_str: str):
    try:
        import pytz
        tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(tz_vn.localize(datetime(dt.year, dt.month, dt.day,  9, 0)).timestamp())
        t_to   = int(tz_vn.localize(datetime(dt.year, dt.month, dt.day, 15, 5)).timestamp())
    except ImportError:
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        t_from = int(datetime(dt.year, dt.month, dt.day, 9, 0).timestamp()) - 25200
        t_to   = int(datetime(dt.year, dt.month, dt.day, 15, 5).timestamp()) - 25200
    return t_from, t_to

def _vn_now():
    try:
        import pytz
        tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
        return datetime.now(tz_vn).replace(tzinfo=None)
    except ImportError:
        return datetime.utcnow() + timedelta(hours=7)

def _is_market_hours(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (t >= datetime.strptime("09:00", "%H:%M").time()) and \
           (t <= datetime.strptime("15:05", "%H:%M").time())

def _is_fresh(df: pd.DataFrame, max_staleness_minutes: int = 12) -> bool:
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
    key = f"VNINDEX|1m|DNSE|{day_str}"
    try:
        t_from, t_to = _day_timestamps(day_str)
        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/index"
        params = {"symbol": "VNINDEX", "resolution": "1", "from": t_from, "to": t_to}
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        t_list = data.get("t") or []
        if not t_list:
            LAST_ERRORS[key] = "DNSE trả về rỗng (có thể ngày nghỉ)."
            return pd.DataFrame()
        LAST_ERRORS.pop(key, None)
        return _build_ohlcv_df(t_list, data["o"], data["h"], data["l"], data["c"], data.get("v"))
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_ssi(day_str: str) -> pd.DataFrame:
    key = f"VNINDEX|1m|SSI|{day_str}"
    t_from, t_to = _day_timestamps(day_str)
    endpoints = [
        "https://iboard-query.ssi.com.vn/v2/stock/history",
        "https://iboard-query.ssi.com.vn/v1/stock/chart",
        "https://iboard.ssi.com.vn/dchart/api/history",
    ]
    headers = {**_INTRADAY_HEADERS, "Referer": "https://iboard.ssi.com.vn/", "Origin": "https://iboard.ssi.com.vn"}
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
            return _build_ohlcv_df(t_list, data["o"], data["h"], data["l"], data["c"], data.get("v"))
        except Exception:
            continue
    LAST_ERRORS[key] = f"SSI: tất cả endpoints đều fail (404/403/empty) cho {day_str}"
    return pd.DataFrame()


def _fetch_intraday_wifeed(day_str: str) -> pd.DataFrame:
    key = f"VNINDEX|1m|WIFEED|{day_str}"
    try:
        t_from, t_to = _day_timestamps(day_str)
        url = "https://wifeed.vn/api/thong-tin-co-phieu/lich-su-gia-theo-phut"
        params = {"symbol": "VNINDEX", "from": t_from, "to": t_to, "resolution": "1"}
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
    key = f"VNINDEX|1m|TCBS|{day_str}"
    try:
        t_from, t_to = _day_timestamps(day_str)
        url = "https://apipubaws.tcbs.com.vn/stock-insight/v1/index/intraday"
        params = {"ticker": "VNINDEX", "type": "1", "from": t_from, "to": t_to}
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") or []
        if not items:
            LAST_ERRORS[key] = "TCBS trả về rỗng."
            return pd.DataFrame()
        df = pd.DataFrame(items)
        rename_map = {
            "tradingDate": "time", "closeIndex": "close", "openIndex": "open",
            "highIndex": "high", "lowIndex": "low", "tradingVolume": "volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        LAST_ERRORS.pop(key, None)
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_vndirect(day_str: str) -> pd.DataFrame:
    key = f"VNINDEX|1m|VNDIRECT|{day_str}"
    try:
        url = "https://api.vndirect.com.vn/v4/market-data/index/history"
        params = {"code": "VNINDEX", "startDate": day_str, "endDate": day_str, "size": 400}
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
    """vnstock VCI/MSN — fallback cuối, dễ bị rate limit. Đua song song 2 nguồn."""
    if not _VNSTOCK_OK:
        return pd.DataFrame()

    def _call(src):
        def _fn():
            _throttle()
            return Quote(symbol=symbol, source=src).history(
                start=day_str, end=day_str, interval='1m'
            )
        return _fn

    tasks = {'VCI': _call('VCI'), 'MSN': _call('MSN')}
    for src, result in _race(tasks, timeout=6):
        key = f"{symbol}|1m|{src}|{day_str}"
        if isinstance(result, Exception):
            LAST_ERRORS[key] = f"{type(result).__name__}: {result}"
            continue
        if result is not None and not result.empty:
            LAST_ERRORS.pop(key, None)
            return _normalize(result)
        LAST_ERRORS[key] = "vnstock trả về rỗng."
    return pd.DataFrame()

def _fetch_intraday_day(symbol: str, day_str: str, require_fresh: bool = False) -> pd.DataFrame:
    """
    Lấy dữ liệu 1 phút cho 1 ngày.
    Thứ tự ưu tiên: DNSE → SSI → Wifeed → TCBS → VNDirect → vnstock (VCI/MSN)

    ĐÃ SỬA BUG: bản cũ, hễ 1 trong 5 nguồn free trả dữ liệu KHÔNG RỖNG là return
    ngay dù dữ liệu đó cũ (không fresh) -> dòng fallback vnstock ở cuối không
    bao giờ chạy tới, nên nếu 1 nguồn free bị cache/stale phía server của họ,
    app mãi mãi kẹt ở đúng 1 mốc giờ cũ dù reboot bao nhiêu lần.

    Bản sửa: khi require_fresh=True và không nguồn free nào đủ mới, BẮT BUỘC
    thử thêm vnstock rồi so sánh timestamp mới nhất giữa TẤT CẢ nguồn đã thử
    (kể cả vnstock), trả về bản có dữ liệu mới nhất tìm được.
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
    best_source_name = None

    def _consider(df, source_name):
        nonlocal best_df, best_last_time, best_source_name
        if df is None or df.empty:
            return
        last_time = df["time"].max()
        if best_last_time is None or (pd.notna(last_time) and last_time > best_last_time):
            best_df = df
            best_last_time = last_time
            best_source_name = source_name

    if symbol == "VNINDEX":
        for fetcher in fetchers:
            df = fetcher(day_str)
            if df.empty:
                continue

            if not require_fresh or _is_fresh(df):
                return df  # đủ mới (hoặc không cần fresh) -> dùng luôn

            # Không fresh -> chỉ giữ làm ứng viên, KHÔNG return ngay
            _consider(df, fetcher.__name__)

        # Đã thử hết 5 nguồn free mà không nguồn nào đủ mới -> bắt buộc thử vnstock
        if require_fresh:
            df_vnstock = _fetch_intraday_vnstock(symbol, day_str)
            _consider(df_vnstock, "vnstock(VCI/MSN)")

        if not best_df.empty:
            if require_fresh and not _is_fresh(best_df):
                LAST_ERRORS[f"VNINDEX|1m|freshness|{day_str}"] = (
                    f"Không nguồn nào (kể cả vnstock) đủ mới — dùng bản mới nhất "
                    f"tìm được từ '{best_source_name}' (cập nhật lúc {best_last_time})."
                )
            else:
                LAST_ERRORS.pop(f"VNINDEX|1m|freshness|{day_str}", None)
            return best_df

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

    now_vn     = _vn_now()
    end_date   = now_vn.strftime('%Y-%m-%d')
    start_date = (now_vn - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch(ticker, start_date, end_date, '1D')

@st.cache_data(ttl=3600, show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=365):
    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch('VNINDEX', start_date, end_date, '1D')

@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex(_cache_bust: int = 0):
    """
    _cache_bust: truyền int thay đổi mỗi lần gọi để buộc tạo cache key mới.
    LƯU Ý: tham số bắt đầu bằng "_" bị Streamlit BỎ QUA khi tính hash cache key
    -> đổi giá trị này KHÔNG thực sự force refresh. ttl=60 vẫn là cơ chế làm
    mới thật sự đang hoạt động (refresh mỗi 60s khi có rerun xảy ra).
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


@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_stock(ticker: str, days: int = 3, _cache_bust: int = 0):
    """
    Bản tổng quát của get_intraday_vnindex() — lấy dữ liệu 1 phút cho MỘT MÃ
    CỔ PHIẾU bất kỳ (không chỉ VNINDEX), gộp nhiều phiên gần nhất lại để đủ
    số nến cho các chỉ báo cần lookback dài (vd Ichimoku Senkou B = 52 nến).

    days: số phiên (ngày giao dịch) tối thiểu muốn gộp. Với khung 5 phút,
    mỗi phiên có ~54 nến, nên days=3 cho ~160 nến 5' -> đủ cho Kijun(26)/
    SenkouB(52) + dịch mây 26 nến.
    """
    frames = []
    for offset in range(15):
        day = (datetime.now() - timedelta(days=offset)).strftime('%Y-%m-%d')
        df_day = _fetch_intraday_day(ticker, day, require_fresh=(offset == 0))
        if not df_day.empty:
            frames.append(df_day)
        if len(frames) >= days:
            break

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result = result.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return result
