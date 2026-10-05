"""
tcbs_client.py - Lấy dữ liệu trực tiếp từ API công khai của TCBS (TCInvest),
thay thế hoàn toàn vnstock cho Fairy-stock.

Cung cấp:
  history(symbol, start, end, interval)  -> DataFrame [time, open, high, low, close, volume]
  financial_ratio(ticker, quarterly)     -> DataFrame (P/E, P/B, ROE, ...)
  overview(ticker)                       -> dict (exchange, outstandingShare, ngành, ...)
  valuation_snapshot(ticker, price)      -> dict {pe, pb, market_cap_bn, outstanding_share_m}
  list_symbols(exchange)                 -> list[str]  (xem ghi chú ở list_symbols)
  set_rate_limit(n) / get_last_error()

Cấu hình qua biến môi trường (tuỳ chọn):
  TCBS_BASE_URL       mặc định https://apipubaws.tcbs.com.vn
  TCBS_TOKEN          Bearer token nếu bạn có (API công khai không cần)
  TCBS_RATE_LIMIT     số request/phút, mặc định 100
  TCBS_PRICE_DIVISOR  mặc định 1000 -> giá cổ phiếu trả về theo đơn vị "nghìn đồng"
                      giống vnstock cũ (20.15 thay vì 20150). Đặt 1 để giữ nguyên VNĐ.
                      Chỉ áp dụng cho cổ phiếu, KHÔNG áp dụng cho chỉ số.
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

# ----------------------------------------------------------------------------
# ENDPOINTS - gom hết một chỗ để dễ sửa nếu TCBS đổi đường dẫn
# ----------------------------------------------------------------------------
BASE_URL = os.getenv("TCBS_BASE_URL", "https://apipubaws.tcbs.com.vn").rstrip("/")
BARS_URL = BASE_URL + os.getenv("TCBS_BARS_PATH", "/stock-insight/v1/stock/bars-long-term")
OVERVIEW_URL = BASE_URL + "/tcanalysis/v1/ticker/{ticker}/overview"
RATIO_URL = BASE_URL + "/tcanalysis/v1/finance/{ticker}/financialratio"

INDEXES = {"VNINDEX", "VN30", "HNX", "HNXINDEX", "HNX30", "UPCOM", "UPCOMINDEX", "VN100"}
_INDEX_ALIAS = {"HNX": "HNXINDEX", "UPCOMINDEX": "UPCOM"}

# interval của app (kiểu vnstock) -> resolution của TCBS
_RESOLUTION = {
    "1m": "1", "5m": "5", "15m": "15", "30m": "30", "1H": "60",
    "1D": "D", "1W": "W", "1M": "M",
}
# số ngày lịch tối đa cho mỗi lần gọi (TCBS giới hạn ~250 nến/lần)
_CHUNK_DAYS = {"D": 340, "W": 1700, "M": 7000, "60": 60, "30": 30, "15": 15, "5": 7, "1": 5}

PRICE_DIVISOR = float(os.getenv("TCBS_PRICE_DIVISOR", "1000"))
_TICKERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tickers.json")

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Accept-Language": "vi",
    "Content-Type": "application/json",
    "Origin": "https://tcinvest.tcbs.com.vn",
    "Referer": "https://tcinvest.tcbs.com.vn/",
}

_session = requests.Session()
_lock = threading.Lock()
_calls = []
_rate_limit_per_min = int(os.getenv("TCBS_RATE_LIMIT", "100"))
_last_error = None


def set_rate_limit(requests_per_minute: int):
    global _rate_limit_per_min
    _rate_limit_per_min = max(1, int(requests_per_minute))


def get_last_error():
    """Lỗi gần nhất khi gọi TCBS (None nếu không có) - để hiện lên UI khi cần debug."""
    return _last_error


def _throttle():
    with _lock:
        now = time.time()
        while _calls and now - _calls[0] > 60:
            _calls.pop(0)
        if len(_calls) >= _rate_limit_per_min:
            wait = 60 - (now - _calls[0]) + 0.05
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _calls and now - _calls[0] > 60:
                _calls.pop(0)
        _calls.append(now)


def _get_json(url, params=None, retries=3, timeout=15):
    """GET + retry/backoff. Trả về JSON hoặc None (và ghi _last_error)."""
    global _last_error
    headers = dict(_HEADERS)
    token = os.getenv("TCBS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for i in range(retries):
        _throttle()
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                _last_error = None
                return r.json()
            _last_error = f"HTTP {r.status_code} @ {url}"
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (i + 1))
                continue
            return None  # 400/401/403/404...: thử lại cũng vô ích
        except (requests.RequestException, ValueError) as e:
            _last_error = f"{type(e).__name__}: {e} @ {url}"
            time.sleep(1.0 * (i + 1))
    return None


# ----------------------------------------------------------------------------
# GIÁ LỊCH SỬ
# ----------------------------------------------------------------------------
def _to_unix(d, end_of_day=False):
    d = pd.Timestamp(d).normalize()
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    ts = int(dt.timestamp())
    return ts + 86399 if end_of_day else ts


def _parse_bars(js, resolution):
    rows = (js or {}).get("data") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "tradingDate" not in df.columns:
        return pd.DataFrame()
    t = pd.to_datetime(df["tradingDate"], errors="coerce", utc=True)
    if resolution in ("D", "W", "M"):
        df["time"] = t.dt.tz_localize(None)                       # giữ nguyên ngày giao dịch
    else:
        df["time"] = t.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    return df[["time", "open", "high", "low", "close", "volume"]]


def history(symbol, start, end, interval="1D", price_divisor=None):
    """Lịch sử OHLCV. start/end: 'YYYY-MM-DD'. Trả về DataFrame rỗng nếu lỗi."""
    symbol = str(symbol).upper().strip()
    is_index = symbol in INDEXES
    ticker = _INDEX_ALIAS.get(symbol, symbol)
    res = _RESOLUTION.get(interval, interval)
    step = _CHUNK_DAYS.get(res, 340)

    start_d, end_d = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    frames, cur = [], start_d
    while cur <= end_d:
        chunk_end = min(cur + timedelta(days=step - 1), end_d)
        js = _get_json(BARS_URL, params={
            "ticker": ticker,
            "type": "index" if is_index else "stock",
            "resolution": res,
            "from": _to_unix(cur),
            "to": _to_unix(chunk_end, end_of_day=True),
        })
        part = _parse_bars(js, res)
        if not part.empty:
            frames.append(part)
        cur = chunk_end + timedelta(days=1)

    if not frames:
        return pd.DataFrame()
    df = (pd.concat(frames).drop_duplicates(subset="time")
          .sort_values("time").reset_index(drop=True))

    div = PRICE_DIVISOR if price_divisor is None else price_divisor
    if not is_index and div and div != 1:
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] / div
    return df


# ----------------------------------------------------------------------------
# CƠ BẢN / ĐỊNH GIÁ
# ----------------------------------------------------------------------------
def overview(ticker):
    js = _get_json(OVERVIEW_URL.format(ticker=str(ticker).upper().strip()))
    return js if isinstance(js, dict) else {}


def financial_ratio(ticker, quarterly=True):
    """Chỉ số tài chính theo quý/năm, dòng đầu = kỳ mới nhất."""
    js = _get_json(RATIO_URL.format(ticker=str(ticker).upper().strip()),
                   params={"yearly": 0 if quarterly else 1, "isAll": "false"})
    if isinstance(js, dict):
        js = js.get("data", js.get("items", []))
    if not isinstance(js, list) or not js:
        return pd.DataFrame()
    return pd.DataFrame(js)


def valuation_snapshot(ticker, price_vnd=None):
    """P/E, P/B, vốn hoá (tỷ VNĐ) cho 1 mã. price_vnd: giá VNĐ đầy đủ (vd 20150)."""
    out = {"pe": 0.0, "pb": 0.0, "outstanding_share_m": 0.0, "market_cap_bn": 0.0}
    ov = overview(ticker)
    shares = ov.get("outstandingShare")           # đơn vị: triệu cổ phiếu
    if shares is not None:
        out["outstanding_share_m"] = float(shares)
        if price_vnd:
            out["market_cap_bn"] = float(shares) * float(price_vnd) / 1000.0

    df = financial_ratio(ticker, quarterly=True)
    if not df.empty:
        row = df.iloc[0]
        for key, col in (("pe", "priceToEarning"), ("pb", "priceToBook")):
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v):
                out[key] = float(v)
    return out


# ----------------------------------------------------------------------------
# DANH SÁCH MÃ
# ----------------------------------------------------------------------------
def list_symbols(exchange="all"):
    """
    Danh sách mã theo sàn, đọc từ tickers.json cạnh file này:
        [{"symbol": "HPG", "exchange": "HOSE"}, ...]
    (hoặc đơn giản ["HPG", "SSI", ...]).
    TCBS không có endpoint công khai ổn định để liệt kê toàn bộ mã nên danh sách
    được giữ trong file và làm mới định kỳ - xem hướng dẫn trong phần giải thích.
    """
    try:
        with open(_TICKERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    out = []
    want = None
    if str(exchange).lower() != "all":
        want = "HOSE" if str(exchange).upper() in ("HOSE", "HSX") else str(exchange).upper()
    for item in data:
        if isinstance(item, str):
            if want is None:
                out.append(item.strip().upper())
            continue
        sym = str(item.get("symbol", "")).strip().upper()
        ex = str(item.get("exchange", "")).strip().upper()
        ex = "HOSE" if ex == "HSX" else ex
        if sym and (want is None or ex == want):
            out.append(sym)
    return out
