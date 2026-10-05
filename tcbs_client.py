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
  TCBS_API_KEY        API key iFlash Open API (chỉ dùng để đổi lấy JWT, cần kèm OTP)
  TCBS_OTP            Smart OTP (iOTP) từ app TCInvest - dùng 1 lần khi đăng nhập
  TCBS_OPENAPI_URL    mặc định https://openapi.tcbs.com.vn
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

OPENAPI_URL = os.getenv("TCBS_OPENAPI_URL", "https://openapi.tcbs.com.vn").rstrip("/")

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
_jwt = os.getenv("TCBS_JWT")  # có thể truyền sẵn JWT nếu đã có


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


def _get_json(url, params=None, retries=3, timeout=15, auth=False):
    """GET + retry/backoff. Trả về JSON hoặc None (và ghi _last_error)."""
    global _last_error, _jwt
    headers = dict(_HEADERS)
    # JWT của iFlash chỉ được gửi tới openapi.tcbs.com.vn (auth=True).
    # API key gốc KHÔNG BAO GIỜ gửi tới các endpoint công khai.
    if auth:
        if not _jwt:
            _last_error = "Chưa đăng nhập iFlash (cần iflash_login với OTP)"
            return None
        headers["Authorization"] = f"Bearer {_jwt}"
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
            if r.status_code == 401 and auth:
                _jwt = None
                _last_error = "JWT hết hạn/không hợp lệ - cần iflash_login lại bằng OTP mới"
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


# ----------------------------------------------------------------------------
# iFLASH OPEN API (openapi.tcbs.com.vn) - cần API key + Smart OTP
# ----------------------------------------------------------------------------
# Theo tài liệu chính thức (developers.tcbs.com.vn): POST /gaia/v1/oauth2/openapi/token
# với {"apiKey", "otp"} -> JWT, gắn dạng Bearer cho các request sau.
# LƯU Ý: nhóm "Thị trường" của iFlash chỉ có giá snapshot/realtime, khớp lệnh trong phiên,
# cung cầu, room ngoại, thông tin chứng khoán. KHÔNG có nến lịch sử nhiều ngày và KHÔNG có
# P/E, P/B -> history() và valuation_snapshot() vẫn dùng endpoint công khai ở trên.
def iflash_login(otp=None, api_key=None):
    """Đổi API key + OTP lấy JWT. Trả về True nếu thành công."""
    global _jwt, _last_error
    api_key = api_key or os.getenv("TCBS_API_KEY")
    otp = otp or os.getenv("TCBS_OTP")
    if not api_key or not otp:
        _last_error = "Thiếu TCBS_API_KEY hoặc OTP"
        return False
    try:
        _throttle()
        r = _session.post(
            OPENAPI_URL + "/gaia/v1/oauth2/openapi/token",
            json={"apiKey": api_key, "otp": str(otp)},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        tok = r.json().get("token") if r.status_code == 200 else None
        if tok:
            _jwt = tok
            _last_error = None
            return True
        _last_error = f"Đăng nhập iFlash thất bại: HTTP {r.status_code}"
    except (requests.RequestException, ValueError) as e:
        _last_error = f"Đăng nhập iFlash lỗi: {type(e).__name__}"
    return False


def iflash_logged_in():
    return bool(_jwt)


def iflash_snapshot(tickers=None, index=None):
    """
    GET /tartarus/v1/tickerCommons (mục 5.1) - giá hiện tại/trần/sàn/tham chiếu, OHLC trong ngày.
    tickers: list mã (không dùng chung với index).
    index: 1=HOSE 2=VN30 3=HNX 4=HNX30 5=UPCOM 11=VN100 15=VN50 ...
    """
    params = {}
    if tickers:
        params["tickers"] = ",".join(str(t).upper() for t in tickers)
    elif index is not None:
        params["index"] = index
    js = _get_json(OPENAPI_URL + "/tartarus/v1/tickerCommons", params=params, auth=True)
    rows = (js or {}).get("data") or []
    return pd.DataFrame(rows)


_TRADE_PLACE = {"001": "HOSE", "002": "HNX", "005": "UPCOM"}


def iflash_securities(max_pages=10):
    """
    GET /ananke/v1/securities (mục 5.11) - toàn bộ chứng khoán niêm yết, có phân trang
    (mặc định 1000 bản ghi/trang). Tài liệu không nêu tên tham số trang; dùng `page`
    theo chuẩn Spring (response có number/totalPages/last) và tự dừng nếu trang lặp.
    """
    rows, first_sym = [], None
    for page in range(max_pages):
        params = {"fields": "all"}
        if page:
            params["page"] = page
        js = _get_json(OPENAPI_URL + "/ananke/v1/securities", params=params, auth=True)
        if not isinstance(js, dict):
            break
        content = js.get("content") or []
        if not content:
            break
        if page and content[0].get("symbol") == first_sym:
            break  # server bỏ qua tham số trang -> tránh lặp vô hạn
        if page == 0:
            first_sym = content[0].get("symbol")
        rows.extend(content)
        if js.get("last", True) or page + 1 >= int(js.get("totalPages") or 1):
            break
    return rows


def sync_symbols(path=None):
    """
    Ghi tickers.json = cổ phiếu phổ thông HOSE/HNX/UPCOM (cần đã đăng nhập iFlash).
    Nguồn chính: 5.11 securities (secType=001, tradePlace, status=Y) - lọc chính xác theo loại.
    Dự phòng: 5.1 tickerCommons theo rổ 1/3/5, chỉ giữ mã 3 ký tự.
    Trả về số mã đã ghi (0 nếu lỗi).
    """
    out, seen = [], set()
    for it in iflash_securities():
        sym = str(it.get("symbol", "")).strip().upper()
        ex = _TRADE_PLACE.get(str(it.get("tradePlace")))
        if (sym and ex and str(it.get("secType")) == "001"
                and str(it.get("status", "Y")) == "Y" and sym not in seen):
            seen.add(sym)
            out.append({"symbol": sym, "exchange": ex})

    if not out:  # dự phòng
        for idx, ex in ((1, "HOSE"), (3, "HNX"), (5, "UPCOM")):
            df = iflash_snapshot(index=idx)
            if df.empty or "symbol" not in df.columns:
                continue
            for sym in df["symbol"].astype(str).str.strip().str.upper():
                if len(sym) == 3 and sym.isalnum() and sym not in seen:
                    seen.add(sym)
                    out.append({"symbol": sym, "exchange": ex})
    if not out:
        return 0
    with open(path or _TICKERS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    return len(out)
