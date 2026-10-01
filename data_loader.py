import streamlit as st
import pandas as pd
import os
import time
import threading
import concurrent.futures
import requests as _requests
from datetime import datetime, timedelta

import tcbs_data  # nguồn giá trực tiếp từ TCBS (thay cho vnstock)


def _fetch_dnse(symbol, days_back=350):
    """DNSE Chart API — public, không cần auth."""
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
    """So sánh ngày dữ liệu MỚI NHẤT trong df với ngày giao dịch kỳ vọng."""
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


# [VÁ 1] Khoá cache theo ngày giao dịch kỳ vọng + nạp dữ liệu có bù ngày thiếu
def _daily_bucket():
    """Khoá cache cho dữ liệu NGÀY: đổi đúng lúc 'ngày giao dịch kỳ vọng' đổi
    (17:00 hằng ngày / qua nửa đêm), nên cache cũ tự mất hiệu lực thay vì sống tới 1 giờ."""
    return str(get_expected_latest_trading_date(_vn_now()))


def _load_stock(ticker, days_back):
    """Supabase là nền; nếu nến mới nhất cũ hơn ngày kỳ vọng thì chỉ gọi API bù phần thiếu rồi gộp."""
    now_vn = _vn_now()
    cached = _read_from_cache(ticker, days_back)

    if cached is not None and len(cached) >= min(60, days_back // 2):
        if not get_data_freshness(cached, now_vn)["is_stale"]:
            return cached
        last = pd.to_datetime(cached["time"].max())
        start = (last - timedelta(days=5)).strftime('%Y-%m-%d')
        fresh = _fetch(ticker, start, now_vn.strftime('%Y-%m-%d'), '1D')
        if fresh is not None and not fresh.empty:
            merged = pd.concat([cached, fresh], ignore_index=True)
            merged = (merged.drop_duplicates(subset="time", keep="last")
                            .sort_values("time").reset_index(drop=True))
            return merged
        return cached  # API lỗi: vẫn hơn là không có gì (banner độ trễ ở UI sẽ báo)

    start = (now_vn - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch(ticker, start, now_vn.strftime('%Y-%m-%d'), '1D')


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
        # Luôn trả cache Supabase ngay (banner độ trễ + nút "Làm mới" ở UI lo phần refresh)
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
    """Ngủ NGOÀI lock để các luồng khác không bị đứng khựng theo."""
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
SCREENER_CACHE_FILE = "screener_cache.xlsx"

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
# YAHOO FINANCE (fallback cuối cho dữ liệu daily)
# ==========================================================
# [VÁ 4] Sửa mã chỉ số (^VNINDEX) và cộng 1 ngày vì Yahoo loại trừ ngày `end`
def _fetch_yahoo(symbol, start, end):
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        ticker = "^VNINDEX" if symbol == "VNINDEX" else f"{symbol}.VN"
        end_incl = (pd.Timestamp(end) + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.Ticker(ticker).history(start=start, end=end_incl)
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
    ĐUA nhiều nguồn CÙNG LÚC. Trả về list [(tên_nguồn, kết_quả_hoặc_Exception)]
    theo thứ tự hoàn thành; nguồn nào chưa xong khi hết giờ sẽ bị bỏ qua.
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
# FETCH DAILY (lịch sử dài hạn): TCBS + DNSE đua song song, Yahoo dự phòng
# ==========================================================
def _fetch(symbol, start, end, interval):
    if interval != '1D':
        return pd.DataFrame()

    expected_date = get_expected_latest_trading_date()
    best_df = pd.DataFrame()
    best_last_date = None

    def _last_date(d):
        if d is None or d.empty or 'time' not in d.columns:
            return None
        v = pd.to_datetime(d['time'].max())
        return v.date() if pd.notna(v) else None

    def _call_tcbs():
        _throttle()
        # [VÁ 5] Cộng 1 ngày vào `end`: nhiều API coi `end` là mốc loại trừ nên mất nến hôm nay.
        # Nếu tcbs_data đã tự xử lý (end bao gồm), dòng này vô hại; nếu thấy lỗi thì đổi lại thành `end`.
        end_incl = (datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        return tcbs_data.fetch_bars_range(symbol, start, end_incl, 'D')

    days = (datetime.strptime(end, '%Y-%m-%d') -
            datetime.strptime(start, '%Y-%m-%d')).days + 10
    tasks = {
        'TCBS': _call_tcbs,
        'DNSE': lambda: _fetch_dnse(symbol, days_back=days),
    }

    for src, result in _race(tasks, timeout=8):
        key = f"{symbol}|{interval}|{src}"
        if isinstance(result, Exception):
            LAST_ERRORS[key] = f"{type(result).__name__}: {result}"
            continue
        df = result
        if df is None or df.empty:
            LAST_ERRORS[key] = "API trả về DataFrame rỗng."
            continue
        LAST_ERRORS.pop(key, None)
        df = tcbs_data.scale_to_thousand(_normalize(df), symbol)
        ld = _last_date(df)
        if expected_date is None or (ld is not None and ld >= expected_date):
            return df
        if best_last_date is None or (ld is not None and ld > best_last_date):
            best_df, best_last_date = df, ld
        LAST_ERRORS[key] = f"{src} chỉ có dữ liệu tới {ld} (kỳ vọng {expected_date})."

    if not best_df.empty:
        return best_df

    df_yahoo = _run_with_timeout(lambda: _fetch_yahoo(symbol, start, end), timeout=5)
    if df_yahoo is not None and not df_yahoo.empty:
        return tcbs_data.scale_to_thousand(_normalize(df_yahoo), symbol)

    return best_df

# ==========================================================
# INTRADAY
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

# ---------- Nguồn intraday cho VNINDEX ----------
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

# ---------- Nguồn intraday chung (dùng cho CỔ PHIẾU, và VNINDEX dự phòng) ----------
def _fetch_intraday_tcbs_bars(symbol: str, day_str: str) -> pd.DataFrame:
    """Nến 1 phút từ API bars của TCBS (dùng được cho cả cổ phiếu và chỉ số)."""
    key = f"{symbol}|1m|TCBSBARS|{day_str}"
    try:
        _throttle()
        df = tcbs_data.fetch_bars(symbol, day_str, day_str, '1')
        if df is None or df.empty:
            LAST_ERRORS[key] = "TCBS bars trả về rỗng."
            return pd.DataFrame()
        LAST_ERRORS.pop(key, None)
        return _normalize(df)
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_stock_dnse(symbol: str, day_str: str) -> pd.DataFrame:
    """Nến 1 phút cổ phiếu từ DNSE (Entrade)."""
    key = f"{symbol}|1m|DNSE|{day_str}"
    try:
        _throttle()
        t_from, t_to = _day_timestamps(day_str)
        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
        params = {"symbol": symbol.upper(), "resolution": "1", "from": t_from, "to": t_to}
        r = _requests.get(url, params=params, headers=_INTRADAY_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        t_list = data.get("t") or []
        if not t_list:
            LAST_ERRORS[key] = "DNSE trả về rỗng (có thể ngày nghỉ)."
            return pd.DataFrame()
        LAST_ERRORS.pop(key, None)
        df = _build_ohlcv_df(t_list, data["o"], data["h"], data["l"], data["c"], data.get("v"))
        return tcbs_data.scale_to_thousand(df, symbol)
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def _fetch_intraday_day(symbol: str, day_str: str, require_fresh: bool = False) -> pd.DataFrame:
    """
    Lấy dữ liệu 1 phút cho 1 ngày.
      VNINDEX : DNSE -> SSI -> Wifeed -> TCBS(index/intraday) -> VNDirect -> TCBS bars
      Cổ phiếu: DNSE -> TCBS bars
    Khi require_fresh=True mà không nguồn nào đủ mới, trả về bản có timestamp
    mới nhất tìm được (thay vì kẹt ở nguồn đầu tiên trả dữ liệu cũ).
    """
    if symbol == "VNINDEX":
        fetchers = [
            ("DNSE", _fetch_intraday_dnse),
            ("SSI", _fetch_intraday_ssi),
            ("WIFEED", _fetch_intraday_wifeed),
            ("TCBS", _fetch_intraday_tcbs),
            ("VNDIRECT", _fetch_intraday_vndirect),
            ("TCBS_BARS", lambda d: _fetch_intraday_tcbs_bars("VNINDEX", d)),
        ]
    else:
        fetchers = [
            ("DNSE", lambda d: _fetch_intraday_stock_dnse(symbol, d)),
            ("TCBS_BARS", lambda d: _fetch_intraday_tcbs_bars(symbol, d)),
        ]

    best_df = pd.DataFrame()
    best_last_time = None
    best_source_name = None

    for name, fn in fetchers:
        df = fn(day_str)
        if df is None or df.empty:
            continue
        if not require_fresh or _is_fresh(df):
            return df
        last_time = df["time"].max()
        if best_last_time is None or (pd.notna(last_time) and last_time > best_last_time):
            best_df, best_last_time, best_source_name = df, last_time, name

    fresh_key = f"{symbol}|1m|freshness|{day_str}"
    if not best_df.empty:
        LAST_ERRORS[fresh_key] = (
            f"Không nguồn nào đủ mới — dùng bản mới nhất từ '{best_source_name}' "
            f"(cập nhật lúc {best_last_time})."
        )
        return best_df
    return pd.DataFrame()

# ==========================================================
# DANH SÁCH MÃ
# ==========================================================
def _listing_vndirect(exchange):
    """Danh sách mã đang niêm yết (kèm sàn) từ API finfo công khai của VNDirect."""
    r = _requests.get(
        "https://finfo-api.vndirect.com.vn/v4/stocks",
        params={"q": "type:STOCK~status:LISTED", "fields": "code,floor", "size": 3000},
        headers=_INTRADAY_HEADERS, timeout=15,
    )
    r.raise_for_status()
    items = r.json().get("data") or []
    if exchange != 'all':
        tgt = 'HOSE' if str(exchange).upper() in ('HOSE', 'HSX') else str(exchange).upper()
        items = [it for it in items if str(it.get("floor", "")).upper() == tgt]
    lst = [str(it.get("code", "")).strip().upper() for it in items]
    return [t for t in lst if t]

def _listing_screener_cache():
    """Dự phòng: lấy danh sách mã từ file cache của bot quét (cột 'Mã CP')."""
    if not os.path.exists(SCREENER_CACHE_FILE):
        return []
    df = pd.read_excel(SCREENER_CACHE_FILE, sheet_name="scan")
    if "Mã CP" not in df.columns:
        return []
    return [str(t).strip().upper() for t in df["Mã CP"].dropna().tolist() if str(t).strip()]

@st.cache_data(ttl=86400, show_spinner=False)
def _get_all_tickers_cached(exchange='all'):
    # Ném lỗi nếu thất bại -> Streamlit KHÔNG cache kết quả lỗi trong 24 giờ
    lst = _listing_vndirect(exchange)
    if not lst:
        raise RuntimeError("Danh sách mã trả về rỗng.")
    return lst

def get_all_tickers(exchange='all'):
    try:
        return _get_all_tickers_cached(exchange)
    except Exception as e:
        LAST_ERRORS["get_all_tickers|vndirect"] = f"{type(e).__name__}: {e}"
    try:
        lst = _listing_screener_cache()
        if lst:
            return lst
    except Exception as e:
        LAST_ERRORS["get_all_tickers|screener_cache"] = f"{type(e).__name__}: {e}"
    return FALLBACK_TICKERS

# Giữ tương thích với chỗ nào đó gọi get_all_tickers.clear()
get_all_tickers.clear = _get_all_tickers_cached.clear

# ==========================================================
# PUBLIC API
# ==========================================================
# [VÁ 2] get_stock_data / get_vnindex_data: khoá cache theo ngày giao dịch, không cache kết quả rỗng
@st.cache_data(ttl=3600, show_spinner=False)
def _cached_stock(ticker, days_back, bucket):
    df = _load_stock(ticker, days_back)
    if df is None or df.empty:
        # Ném lỗi để Streamlit KHÔNG cache kết quả rỗng suốt 1 giờ
        raise ValueError("empty")
    return df


def get_stock_data(ticker, days_back=200):
    try:
        return _cached_stock(ticker, days_back, _daily_bucket())
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_vnindex(days_back, bucket):
    now_vn = _vn_now()
    df = _fetch('VNINDEX',
                (now_vn - timedelta(days=days_back)).strftime('%Y-%m-%d'),
                now_vn.strftime('%Y-%m-%d'), '1D')
    if df is None or df.empty:
        raise ValueError("empty")
    return df


def get_vnindex_data(ticker="VNINDEX", days_back=365):
    try:
        return _cached_vnindex(days_back, _daily_bucket())
    except Exception:
        return pd.DataFrame()


# Giữ tương thích với chỗ nào đó gọi get_stock_data.clear() / get_vnindex_data.clear()
get_stock_data.clear = _cached_stock.clear
get_vnindex_data.clear = _cached_vnindex.clear


@st.cache_data(ttl=60, show_spinner=False)
def get_intraday_vnindex(_cache_bust: int = 0):
    """
    LƯU Ý: tham số bắt đầu bằng "_" bị Streamlit BỎ QUA khi tính cache key,
    nên ttl=60 mới là cơ chế làm mới thật sự.
    """
    frames = []
    for offset in range(6):
        # [VÁ 3] dùng giờ VN thay vì datetime.now() (UTC trên Streamlit Cloud)
        day = (_vn_now() - timedelta(days=offset)).strftime('%Y-%m-%d')
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
    Dữ liệu 1 phút của MỘT MÃ cổ phiếu, gộp nhiều phiên gần nhất để đủ số nến
    cho chỉ báo cần lookback dài (vd Ichimoku Senkou B = 52 nến).
    """
    frames = []
    for offset in range(15):
        # [VÁ 3] dùng giờ VN thay vì datetime.now() (UTC trên Streamlit Cloud)
        day = (_vn_now() - timedelta(days=offset)).strftime('%Y-%m-%d')
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
