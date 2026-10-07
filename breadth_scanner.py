"""
breadth_scanner.py — Quét sức khỏe thị trường HOSE, ghi breadth.json
Chạy qua GitHub Actions "Scan Breadth HOSE" — sau khi đóng cửa phiên chiều (3 mốc cron dự phòng).

BẢN CẬP NHẬT (so với bản vnstock-chính):
  1. NGUỒN GIÁ CHÍNH = TCBS (bars-long-term). DNSE / FireAnt / Yahoo là dự phòng.
     vnstock chỉ còn dùng để lấy danh sách mã và (nếu có VNSTOCK_API_KEY) làm nguồn giá dự phòng cuối,
     vì không key chỉ 18 request/phút -> 400 mã mất >20 phút và hay trả dữ liệu trễ.
  2. SỬA LỖI KẸT DỮ LIỆU CŨ: quy tắc cũ "đã quét < 180 phút thì bỏ qua" chặn luôn 2 lượt dự phòng
     (17:30 -> 18:30 -> 20:00 đều nằm trong 180 phút). Nếu lượt đầu ghi dữ liệu trễ thì các lượt sau
     không sửa được. Nay chỉ bỏ qua khi breadth.json ĐÃ ĐÚNG phiên mới nhất trên TCBS.
  3. Ngày giao dịch kỳ vọng lấy từ VNINDEX trên TCBS (đúng cả khi nghỉ lễ), không đoán theo lịch T2-T6.
  4. Chỉ tính các mã có phiên mới nhất = data_date; thêm % trên MA100 và khuyến nghị tỷ trọng.
  5. Không ghi đè bằng dữ liệu cũ hơn file hiện có; lỗi thật trả mã thoát 1 để workflow đỏ.
"""

import os, sys, time, json, threading, traceback, requests
import concurrent.futures as _cf
from datetime import datetime, timezone, timedelta, date
from collections import Counter, defaultdict

import pandas as pd

# ──────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────
MIN_LEN_FOR_MA        = 55
MAX_WORKERS           = 6
DEFAULT_RATE_LIMIT    = 18     # chỉ áp dụng khi gọi vnstock không có API key
VN_TZ                 = timezone(timedelta(hours=7))
MARKET_CLOSE_CUTOFF   = "15:40"
MIN_COVERAGE          = 0.6    # dưới mức này coi là quét hỏng
TCBS_URL              = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
UNIVERSE_CSV          = "data/stock_prices.csv"
HEADERS               = {"User-Agent": "Mozilla/5.0"}
HAS_VNSTOCK_KEY       = bool(os.environ.get("VNSTOCK_API_KEY", "").strip())

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
def _vn_now():
    return datetime.now(VN_TZ).replace(tzinfo=None)

def _log(msg):
    print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] {msg}", flush=True)

def _log_err(context, e):
    _log(f"⚠️ [{context}] {type(e).__name__}: {e}")

# ──────────────────────────────────────────────
# RATE LIMIT (chỉ dùng khi gọi vnstock)
# ──────────────────────────────────────────────
_rate_lim  = DEFAULT_RATE_LIMIT
_rate_lock = threading.Lock()
_call_ts   = []

def set_rate_limit(n: int):
    global _rate_lim
    _rate_lim = max(1, int(n))

def _throttle_vnstock():
    with _rate_lock:
        now = time.time()
        while _call_ts and now - _call_ts[0] > 60:
            _call_ts.pop(0)
        if len(_call_ts) >= _rate_lim:
            wait = 60 - (now - _call_ts[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _call_ts and now - _call_ts[0] > 60:
                _call_ts.pop(0)
        _call_ts.append(now)

# ──────────────────────────────────────────────
# THỜI GIAN / NGÀY GIAO DỊCH KỲ VỌNG
# ──────────────────────────────────────────────
def _is_after_market_close(now_vn: datetime) -> bool:
    if now_vn.weekday() >= 5:
        return False
    return now_vn.time() >= datetime.strptime(MARKET_CLOSE_CUTOFF, "%H:%M").time()

def _calendar_expected_date():
    """Ngày kỳ vọng theo lịch T2-T6 (chỉ dùng khi không hỏi được TCBS)."""
    now = datetime.now(VN_TZ)
    d = now.date()
    if now.weekday() < 5 and now.time() < datetime.strptime(MARKET_CLOSE_CUTOFF, "%H:%M").time():
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

_EXPECTED = None   # được gán từ VNINDEX/TCBS ở entry point

def _expected_latest_trading_date():
    return _EXPECTED or _calendar_expected_date()

# ──────────────────────────────────────────────
# NGUỒN CHÍNH: TCBS
# ──────────────────────────────────────────────
def _fetch_tcbs(symbol: str, kind: str = "stock", count_back: int = 160, retries: int = 3):
    params = {"ticker": symbol, "type": kind, "resolution": "D",
              "to": int(time.time()) + 86400, "countBack": count_back}
    for i in range(retries):
        try:
            r = requests.get(TCBS_URL, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                rows = r.json().get("data") or []
                if rows:
                    df = pd.DataFrame(rows)
                    df["time"] = pd.to_datetime(df["tradingDate"].astype(str).str[:10])
                    df["close"] = pd.to_numeric(df["close"], errors="coerce")
                    df = (df.dropna(subset=["close"]).drop_duplicates("time", keep="last")
                            .sort_values("time").reset_index(drop=True))
                    return df if len(df) >= 5 else None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None

# ──────────────────────────────────────────────
# NGUỒN DỰ PHÒNG: vnstock (chỉ khi có API key), DNSE, FireAnt, Yahoo
# ──────────────────────────────────────────────
def _fetch_vnstock(symbol: str) -> pd.DataFrame | None:
    try:
        _throttle_vnstock()
        from vnstock import Market
        end_date   = (datetime.now(VN_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now(VN_TZ) - timedelta(days=240)).strftime("%Y-%m-%d")
        df = Market().equity.ohlcv(symbol=symbol, start=start_date, end=end_date)
        if df is None or (hasattr(df, "empty") and df.empty):
            return None
        df.columns = [str(c).lower().strip() for c in df.columns]
        for col in ["time", "date", "tradingdate", "trading_date"]:
            if col in df.columns:
                df = df.rename(columns={col: "time"})
                break
        if "time" not in df.columns:
            return None
        df["close"] = pd.to_numeric(df.get("close", df.get("closeprice", None)), errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None

def _fetch_dnse(symbol: str) -> pd.DataFrame | None:
    try:
        end_ts = int(datetime.now(VN_TZ).timestamp())
        url = (f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
               f"?from={end_ts - 240*86400}&to={end_ts}&resolution=D&symbol={symbol}")
        r = requests.get(url, timeout=8, headers=HEADERS)
        if r.status_code != 200:
            return None
        d = r.json()
        if not d or "t" not in d or not d["t"]:
            return None
        df = pd.DataFrame({
            "time":  pd.to_datetime(d["t"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None),
            "close": d.get("c", []),
        })
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None

def _fetch_fireant(symbol: str) -> pd.DataFrame | None:
    try:
        end_d   = date.today() + timedelta(days=1)
        start_d = (datetime.now(VN_TZ) - timedelta(days=240)).date()
        url = (f"https://api.fireant.vn/symbols/{symbol}/historical-quotes"
               f"?startDate={start_d}&endDate={end_d}&offset=0&limit=200")
        r = requests.get(url, timeout=8, headers=HEADERS)
        if r.status_code != 200:
            return None
        raw = r.json()
        if not raw:
            return None
        df = pd.DataFrame(raw)
        df = df.rename(columns={c: ("time" if c.lower() == "date" else "close" if c.lower() == "close" else c)
                                for c in df.columns})
        df["time"]  = pd.to_datetime(df["time"]).dt.tz_localize(None)
        df["close"] = pd.to_numeric(df.get("close", 0), errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None

def _fetch_yahoo(symbol: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
        start = (datetime.now(VN_TZ) - timedelta(days=240)).strftime("%Y-%m-%d")
        end   = (datetime.now(VN_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.Ticker(f"{symbol}.VN").history(start=start, end=end, auto_adjust=True)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        for col in df.columns:
            if "date" in col:
                df = df.rename(columns={col: "time"})
                break
        df["time"]  = pd.to_datetime(df["time"]).dt.tz_localize(None)
        df["close"] = pd.to_numeric(df.get("close", 0), errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None

_FALLBACK_SOURCES = [_fetch_dnse, _fetch_fireant, _fetch_yahoo]


def get_price_history(symbol: str, race_timeout: float = 8.0) -> pd.DataFrame | None:
    """TCBS trước; nếu lỗi/trễ thì đua DNSE+FireAnt+Yahoo; cuối cùng vnstock (nếu có key)."""
    expected = _expected_latest_trading_date()
    best = {"df": None, "date": None}

    def consider(d):
        if d is None or d.empty:
            return False
        last_date = pd.to_datetime(d["time"].max()).date()
        if last_date >= expected:
            return True
        if best["date"] is None or last_date > best["date"]:
            best["df"], best["date"] = d, last_date
        return False

    d = _fetch_tcbs(symbol)
    if consider(d):
        return d

    with _cf.ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(fn, symbol) for fn in _FALLBACK_SOURCES]
        try:
            for fut in _cf.as_completed(futures, timeout=race_timeout):
                try:
                    d = fut.result()
                except Exception:
                    continue
                if consider(d):
                    ex.shutdown(wait=False, cancel_futures=True)
                    return d
        except _cf.TimeoutError:
            pass
        ex.shutdown(wait=False, cancel_futures=True)

    if HAS_VNSTOCK_KEY:
        d = _fetch_vnstock(symbol)
        if consider(d):
            return d

    return best["df"]

# ──────────────────────────────────────────────
# DANH SÁCH MÃ HOSE: vnstock → DNSE → FireAnt → data/stock_prices.csv
# ──────────────────────────────────────────────
def _get_hose_tickers_vnstock() -> list:
    try:
        _throttle_vnstock()
        from vnstock import Reference
        ref = Reference()
        df = None
        try:
            df = ref.equity.list_by_exchange()
        except Exception as e:
            _log_err("vnstock Reference.list_by_exchange", e)
        if df is None or (hasattr(df, "empty") and df.empty):
            try:
                df = ref.equity.list()
            except Exception as e:
                _log_err("vnstock Reference.list", e)
        if df is None or (hasattr(df, "empty") and df.empty):
            return []
        df.columns = [str(c).lower().strip() for c in df.columns]
        exch_col = next((c for c in df.columns if "exchange" in c or "floor" in c or "board" in c), None)
        if exch_col:
            df = df[df[exch_col].astype(str).str.upper().isin(["HOSE", "HSX"])]
        type_col = next((c for c in df.columns if "type" in c), None)
        if type_col:
            df = df[df[type_col].astype(str).str.upper().isin(["STOCK", "CP", "CỔ PHIẾU", "EQ", "EQUITY"])]
        col = next((c for c in ["symbol", "ticker", "code"] if c in df.columns), None)
        if not col:
            return []
        tickers = [str(t).strip().upper() for t in df[col].dropna() if str(t).strip()]
        if tickers:
            _log(f"✅ [vnstock Reference] {len(tickers)} mã HOSE")
        return tickers
    except Exception as e:
        _log_err("_get_hose_tickers_vnstock", e)
        return []

def _get_hose_tickers_dnse() -> list:
    try:
        r = requests.get("https://finfo-api.dnse.com.vn/v3/market-data/listing", timeout=8, headers=HEADERS)
        if r.status_code != 200:
            return []
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
        tickers = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("exchange", item.get("floor", ""))).upper() not in ("HOSE", "HSX"):
                continue
            itype = str(item.get("type", item.get("secType", ""))).upper()
            if itype and itype not in ("STOCK", "EQ", "CP", "S"):
                continue
            sym = item.get("symbol", item.get("ticker", item.get("code", "")))
            if sym:
                tickers.append(str(sym).strip().upper())
        if tickers:
            _log(f"✅ [DNSE listing] {len(tickers)} mã HOSE")
        return tickers
    except Exception as e:
        _log_err("_get_hose_tickers_dnse", e)
        return []

def _get_hose_tickers_fireant() -> list:
    try:
        r = requests.get("https://api.fireant.vn/securities?type=1&exchange=HOSE&offset=0&limit=500",
                         timeout=8, headers=HEADERS)
        if r.status_code != 200:
            return []
        items = r.json()
        if not isinstance(items, list):
            items = items.get("data", [])
        tickers = [str(i.get("symbol", i.get("ticker", ""))).strip().upper() for i in items if isinstance(i, dict)]
        tickers = [t for t in tickers if t]
        if tickers:
            _log(f"✅ [FireAnt listing] {len(tickers)} mã HOSE")
        return tickers
    except Exception as e:
        _log_err("_get_hose_tickers_fireant", e)
        return []

def _get_tickers_csv() -> list:
    try:
        t = pd.read_csv(UNIVERSE_CSV, usecols=["ticker"])["ticker"].dropna().astype(str).str.upper()
        out = sorted(set(t))
        if len(out) >= 50:
            _log(f"✅ [{UNIVERSE_CSV}] {len(out)} mã")
            return out
    except Exception as e:
        _log_err("_get_tickers_csv", e)
    return []

def get_hose_tickers() -> list:
    tickers = _get_hose_tickers_vnstock()
    if tickers:
        return tickers
    _log("⚠️ vnstock listing lỗi → thử DNSE/FireAnt")
    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        f1, f2 = ex.submit(_get_hose_tickers_dnse), ex.submit(_get_hose_tickers_fireant)
        a, b = f1.result(), f2.result()
    if a:
        return a
    if b:
        return b
    _log("⚠️ Các API listing đều lỗi → dùng danh sách mã trong repo")
    return _get_tickers_csv()

# ──────────────────────────────────────────────
# TÍNH ĐIỂM
# ──────────────────────────────────────────────
def compute_breadth_score(ad_pct, pct_above_ma50):
    """Giữ nguyên công thức cũ để không lệch lịch sử/giao diện."""
    score = round((ad_pct - 50) / 50 * 4 + (pct_above_ma50 - 50) / 50 * 4)
    return max(-8, min(8, int(score)))

def compute_momentum_note(ad_pct, pct_above_ma20, pct_above_ma50, score):
    if score >= 5:  return "🟢 Thị trường khoẻ toàn diện: đa số mã đang tăng giá và giữ trên các đường MA."
    if score >= 2:  return "🟢 Thị trường tích cực, dòng tiền lan toả ở nhiều mã."
    if score <= -5: return "🔴 Thị trường yếu diện rộng: phần lớn mã giảm giá và gãy các đường MA."
    if score <= -2: return "🟠 Thị trường suy yếu, số mã giảm giá đang chiếm ưu thế."
    return "🟡 Thị trường phân hoá / đi ngang, chưa có xu hướng rõ ràng trên diện rộng."

def _band(p):
    return 2 if p >= 70 else 1 if p >= 55 else 0 if p >= 40 else -1 if p >= 25 else -2

def compute_recommendation(adv_by_date, dec_by_date, n_by_date, p20, p50, p100):
    """Score khuyến nghị: A/D 10 phiên + độ bền 20 phiên + đường A-D vs MA20 + % trên MA20/50/100."""
    peak = max(n_by_date.values())
    dates = [d for d in sorted(n_by_date) if n_by_date[d] >= 0.5 * peak]
    adv = pd.Series([adv_by_date[d] for d in dates], index=dates)
    dec = pd.Series([dec_by_date[d] for d in dates], index=dates)
    a10, d10 = int(adv.tail(10).sum()), int(dec.tail(10).sum())
    n10 = (a10 - d10) / max(a10 + d10, 1) * 100
    b1 = 2 if n10 >= 15 else 1 if n10 >= 5 else 0 if n10 > -5 else -1 if n10 > -15 else -2
    up_days = float((adv.tail(20) > dec.tail(20)).mean() * 100)
    b2 = 1 if up_days >= 60 else -1 if up_days <= 40 else 0
    cum = (adv - dec).cumsum()
    b3 = 1 if cum.iloc[-1] > cum.tail(20).mean() else -1
    sc = b1 + 0.5 * (b2 + b3)
    for p in (p20, p50, p100):
        if p is not None:
            sc += _band(p)
    sc = int(round(sc))
    equity = max(10, min(90, 60 + 10 * sc))
    action = ("TĂNG TỶ TRỌNG" if sc >= 4 else "TĂNG NHẸ" if sc >= 2 else "GIỮ NGUYÊN" if sc >= -1
              else "GIẢM NHẸ" if sc >= -3 else "GIẢM MẠNH")
    hist = [{"d": d, "a": int(adv[d]), "dc": int(dec[d])} for d in dates[-30:]]
    return sc, action, equity, round(up_days, 1), round(a10 / max(d10, 1), 2), hist

# ──────────────────────────────────────────────
# XỬ LÝ 1 MÃ (ThreadPool)
# ──────────────────────────────────────────────
def _process_one(ticker: str) -> dict | None:
    df = get_price_history(ticker)
    if df is None or len(df) < MIN_LEN_FOR_MA:
        return None

    df["ma20"]  = df["close"].rolling(20).mean()
    df["ma50"]  = df["close"].rolling(50).mean()
    df["ma100"] = df["close"].rolling(100).mean()
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close, prev_close = float(last["close"]), float(prev["close"])
    if prev_close <= 0:
        return None

    tail  = df.tail(61)
    dates = pd.to_datetime(tail["time"]).dt.strftime("%Y-%m-%d").tolist()
    cl    = tail["close"].tolist()
    signs = {dates[i]: int(cl[i] > cl[i-1]) - int(cl[i] < cl[i-1]) for i in range(1, len(cl))}

    return {
        "data_date":   pd.to_datetime(last["time"]).strftime("%Y-%m-%d"),
        "sign":        signs[dates[-1]],
        "signs":       signs,
        "above_ma20":  int(pd.notna(last["ma20"])  and close > last["ma20"]),
        "above_ma50":  int(pd.notna(last["ma50"])  and close > last["ma50"]),
        "has_ma100":   bool(pd.notna(last["ma100"])),
        "above_ma100": int(pd.notna(last["ma100"]) and close > last["ma100"]),
        "chg":         (close - prev_close) / prev_close * 100,
    }

# ──────────────────────────────────────────────
# QUÉT TOÀN BỘ
# ──────────────────────────────────────────────
def scan_breadth(max_tickers=None):
    tickers = get_hose_tickers()
    if not tickers:
        return None
    if max_tickers:
        tickers = tickers[:max_tickers]
    _log(f"📊 Quét {len(tickers)} mã (kỳ vọng phiên >= {_expected_latest_trading_date()}, {MAX_WORKERS} luồng)...")

    rows, done = [], 0
    with _cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in _cf.as_completed([ex.submit(_process_one, t) for t in tickers]):
            done += 1
            try:
                r = fut.result()
            except Exception:
                r = None
            if r is not None:
                rows.append(r)
            if done % 50 == 0:
                _log(f"... {done}/{len(tickers)} xong ({len(rows)} hợp lệ)")

    if not rows:
        _log("❌ Không mã nào quét thành công — mọi nguồn giá đang lỗi.")
        return None

    data_date = Counter(r["data_date"] for r in rows).most_common(1)[0][0]
    cur = [r for r in rows if r["data_date"] == data_date]
    n_valid = len(cur)
    coverage = n_valid / len(tickers)
    _log(f"📅 data_date={data_date} | {n_valid}/{len(tickers)} mã đúng phiên "
         f"({len(rows) - n_valid} mã trễ phiên, {len(tickers) - len(rows)} mã lỗi/thiếu)")

    adv = sum(r["sign"] == 1 for r in cur)
    dec = sum(r["sign"] == -1 for r in cur)
    unc = n_valid - adv - dec
    n100 = [r for r in cur if r["has_ma100"]]
    p20  = round(sum(r["above_ma20"] for r in cur) / n_valid * 100, 2)
    p50  = round(sum(r["above_ma50"] for r in cur) / n_valid * 100, 2)
    p100 = round(sum(r["above_ma100"] for r in n100) / len(n100) * 100, 2) if n100 else None
    ad_pct = adv / n_valid * 100

    adv_d, dec_d, n_d = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in cur:
        for d, s in r["signs"].items():
            n_d[d] += 1
            adv_d[d] += s == 1
            dec_d[d] += s == -1
    rec_score, action, equity, up_days, ratio10, hist = compute_recommendation(adv_d, dec_d, n_d, p20, p50, p100)

    score = compute_breadth_score(ad_pct, p50)
    result = {
        "updated_at":      _vn_now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date":       data_date,
        "n_total":         n_valid,
        "coverage":        round(coverage, 3),
        "advance":         adv,
        "decline":         dec,
        "unchanged":       unc,
        "ad_pct":          round(ad_pct, 2),
        "pct_above_ma20":  p20,
        "pct_above_ma50":  p50,
        "pct_above_ma100": p100,
        "breadth_score":   score,
        "momentum_note":   compute_momentum_note(ad_pct, p20, p50, score),
        "ad_change":       round(sum(r["chg"] for r in cur) / n_valid, 3),
        "rec_score":       rec_score,
        "action":          action,
        "equity_pct":      equity,
        "cash_pct":        100 - equity,
        "up_days_20":      up_days,
        "ad_ratio_10d":    ratio10,
        "history":         hist,
        "source":          "tcbs",
    }
    _log(f"✅ A/D {adv}/{dec} | MA20={p20}% MA50={p50}% MA100={p100}% | "
         f"Score={score:+d} | Khuyến nghị {action} ({rec_score:+d}) CP {equity}%/Tiền {100-equity}%")
    return result


def save_to_json(result: dict, path="breadth.json"):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    _log(f"💾 Đã ghi `{path}`.")


def _load_existing(path="breadth.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    try:
        force  = os.environ.get("FORCE_SCAN", "").strip().lower() in ("1", "true", "yes")
        now_vn = _vn_now()

        if not force and not _is_after_market_close(now_vn):
            _log(f"⏭️  Chưa qua giờ đóng cửa ({now_vn:%H:%M}, cần >= {MARKET_CLOSE_CUTOFF}) — bỏ qua.")
            sys.exit(0)

        # Ngày giao dịch mới nhất thực tế theo VNINDEX trên TCBS
        vn = _fetch_tcbs("VNINDEX", kind="index", count_back=5)
        latest = None
        if vn is not None and not vn.empty:
            latest = pd.to_datetime(vn["time"].max()).date()
            _EXPECTED = latest
            _log(f"📅 VNINDEX trên TCBS: phiên mới nhất {latest}")
        else:
            _log("⚠️ Không lấy được VNINDEX từ TCBS — dùng lịch T2-T6 để suy ra ngày kỳ vọng.")

        old = _load_existing()
        if (not force and latest and old.get("data_date") == latest.strftime("%Y-%m-%d")
                and old.get("coverage", 0) >= MIN_COVERAGE):
            _log(f"✅ breadth.json đã là phiên {latest} — không cần quét lại.")
            sys.exit(0)

        api_key = os.environ.get("VNSTOCK_API_KEY", "").strip()
        if api_key:
            try:
                import vnai
                vnai.setup_api_key(api_key)
                set_rate_limit(55)
                _log("🔑 VNSTOCK_API_KEY có — vnstock dùng làm nguồn dự phòng cuối (55/phút)")
            except Exception as e:
                _log_err("setup vnai (bỏ qua)", e)

        max_t  = os.environ.get("MAX_TICKERS")
        result = scan_breadth(max_tickers=int(max_t) if max_t else None)

        if result is None:
            _log("❌ Quét thất bại — không ghi file.")
            sys.exit(1)
        if result["coverage"] < MIN_COVERAGE:
            _log(f"❌ Độ phủ {result['coverage']:.0%} < {MIN_COVERAGE:.0%} — không ghi đè file cũ.")
            sys.exit(1)
        if old.get("data_date") and result["data_date"] < old["data_date"]:
            _log(f"❌ Dữ liệu mới ({result['data_date']}) cũ hơn file hiện có ({old['data_date']}) — không ghi đè.")
            sys.exit(1)

        save_to_json(result)

        if latest and result["data_date"] < latest.strftime("%Y-%m-%d"):
            _log(f"⚠️ Đã ghi nhưng vẫn trễ so với TCBS ({result['data_date']} < {latest}) — lượt dự phòng sẽ thử lại.")
            sys.exit(1)

    except Exception as e:
        _log(f"💥 LỖI KHÔNG LƯỜNG TRƯỚC: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
