"""
breadth_scanner.py — Quét sức khỏe thị trường HOSE, ghi breadth.json
Chạy qua GitHub Actions "Scan Breadth HOSE" — 1 LẦN/NGÀY sau khi đóng cửa phiên chiều.

THAY ĐỔI QUAN TRỌNG (so với bản real-time cũ):
  - Không còn quét mỗi 15 phút trong giờ giao dịch. Thay vào đó, script chỉ chạy
    SAU KHI HOSE ĐÓNG CỬA (mặc định sau 15:40 ICT), lấy đúng dữ liệu giá đóng cửa
    (EOD) của phiên đã kết thúc — ổn định hơn nhiều so với real-time.
  - vnstock đã nâng cấp lên bản 4.x "Unified UI" (Reference/Market/Fundamental),
    các hàm cũ (Vnstock().stock(), listing_companies...) đã bị loại bỏ hoàn toàn.
    Script này đã cập nhật theo API mới và dùng vnstock làm NGUỒN CHÍNH (chính thức,
    ổn định nhất). DNSE / FireAnt / Yahoo Finance chỉ còn là nguồn DỰ PHÒNG.

NGUỒN DỮ LIỆU (theo thứ tự ưu tiên):
  1. vnstock 4.x (Unified UI, nguồn KBS mặc định) — nguồn chính, chính thức
  2. DNSE      — REST API công khai, không cần key
  3. FireAnt   — REST API công khai, không cần key
  4. Yahoo Finance (yfinance) — ticker.VN, không cần key
"""

import os, sys, time, json, threading, traceback, requests
import concurrent.futures as _cf
from datetime import datetime, timezone, timedelta, date
from collections import Counter

import pandas as pd

# ──────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────
MIN_LEN_FOR_MA        = 55
MAX_WORKERS           = 6
DEFAULT_RATE_LIMIT    = 18     # áp dụng khi gọi vnstock (KBS) không có API key
VN_TZ                 = timezone(timedelta(hours=7))
MIN_REFRESH_MINUTES   = 180    # chống chạy trùng nếu lỡ trigger 2 lần trong ngày
DATA_START            = "2025-05-01"

# Giờ được coi là "đã đóng cửa" — chỉ quét SAU mốc này (ICT)
MARKET_CLOSE_CUTOFF   = "15:40"

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
# RATE LIMIT (dùng khi gọi vnstock)
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
# KIỂM TRA THỜI GIAN — chỉ chạy SAU khi đóng cửa
# ──────────────────────────────────────────────
def _is_after_market_close(now_vn: datetime) -> bool:
    """True nếu đang trong ngày giao dịch (T2-T6) VÀ đã qua giờ đóng cửa."""
    if now_vn.weekday() >= 5:
        return False
    cutoff = datetime.strptime(MARKET_CLOSE_CUTOFF, "%H:%M").time()
    return now_vn.time() >= cutoff

def _minutes_since_last_update(path="breadth.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last = datetime.strptime(data["updated_at"], "%Y-%m-%d %H:%M:%S")
        return (_vn_now() - last).total_seconds() / 60
    except FileNotFoundError:
        _log("ℹ️ Chưa có breadth.json — quét ngay.")
        return None
    except Exception as e:
        _log_err("_minutes_since_last_update", e)
        return None

def _expected_latest_trading_date():
    """Ngày giao dịch mới nhất được kỳ vọng có dữ liệu EOD (bỏ qua T7/CN)."""
    now = datetime.now(VN_TZ)
    d = now.date()
    cutoff = datetime.strptime(MARKET_CLOSE_CUTOFF, "%H:%M").time()
    if now.weekday() < 5 and now.time() < cutoff:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

# ──────────────────────────────────────────────
# NGUỒN CHÍNH: vnstock 4.x — Unified UI
# API mới: from vnstock import Market, Reference
#   Reference().equity.list_by_exchange()  -> danh sách mã theo sàn
#   Market().equity.ohlcv(symbol=..., start=..., end=...) -> giá lịch sử (EOD)
# ──────────────────────────────────────────────
def _fetch_vnstock(symbol: str) -> pd.DataFrame | None:
    """Lấy giá lịch sử (EOD) qua vnstock 4.x Unified UI. Có throttle."""
    try:
        _throttle_vnstock()
        from vnstock import Market
        end_date   = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        start_date = (datetime.now(VN_TZ) - timedelta(days=150)).strftime("%Y-%m-%d")

        market = Market()
        df = market.equity.ohlcv(symbol=symbol, start=start_date, end=end_date)

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


# ──────────────────────────────────────────────
# NGUỒN DỰ PHÒNG 1: DNSE (REST API công khai)
# ──────────────────────────────────────────────
def _fetch_dnse(symbol: str) -> pd.DataFrame | None:
    try:
        end_ts = int(datetime.now(VN_TZ).timestamp())
        url = (
            f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
            f"?from={end_ts - 130*86400}&to={end_ts}"
            f"&resolution=D&symbol={symbol}"
        )
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        d = r.json()
        if not d or "t" not in d or not d["t"]:
            return None
        df = pd.DataFrame({
            "time":   pd.to_datetime(d["t"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None),
            "open":   d.get("o", []),
            "high":   d.get("h", []),
            "low":    d.get("l", []),
            "close":  d.get("c", []),
            "volume": d.get("v", []),
        })
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None


# ──────────────────────────────────────────────
# NGUỒN DỰ PHÒNG 2: FireAnt (REST API công khai)
# ──────────────────────────────────────────────
def _fetch_fireant(symbol: str) -> pd.DataFrame | None:
    try:
        end_d   = date.today()
        start_d = (datetime.now(VN_TZ) - timedelta(days=150)).date()
        url = (
            f"https://api.fireant.vn/symbols/{symbol}/historical-quotes"
            f"?startDate={start_d}&endDate={end_d}&offset=0&limit=160"
        )
        r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        raw = r.json()
        if not raw:
            return None
        df = pd.DataFrame(raw)
        rename = {}
        for col in df.columns:
            lc = col.lower()
            if lc == "date":            rename[col] = "time"
            elif lc == "close":         rename[col] = "close"
            elif lc in ("volume", "totalvolume"): rename[col] = "volume"
        df = df.rename(columns=rename)
        df["close"]  = pd.to_numeric(df.get("close",  0), errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None


# ──────────────────────────────────────────────
# NGUỒN DỰ PHÒNG 3: Yahoo Finance (.VN suffix)
# ──────────────────────────────────────────────
def _fetch_yahoo(symbol: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
        start = (datetime.now(VN_TZ) - timedelta(days=150)).strftime("%Y-%m-%d")
        end   = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        df = yf.Ticker(f"{symbol}.VN").history(start=start, end=end, auto_adjust=True)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        for col in df.columns:
            if "date" in col:
                df = df.rename(columns={col: "time"})
                break
        df["close"]  = pd.to_numeric(df.get("close",  0), errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None


_FALLBACK_SOURCES = [_fetch_dnse, _fetch_fireant, _fetch_yahoo]


def get_price_history(symbol: str, race_timeout: float = 5.0) -> pd.DataFrame | None:
    """
    Chiến lược lấy giá EOD:
    Tầng 1 — vnstock 4.x (nguồn chính thức). Nếu dữ liệu đủ mới (>= ngày giao dịch
              kỳ vọng) → dùng luôn.
    Tầng 2 — nếu vnstock lỗi hoặc dữ liệu cũ → đua song song DNSE + FireAnt + Yahoo.
    """
    expected = _expected_latest_trading_date()

    best_df, best_date = None, None

    df = _fetch_vnstock(symbol)
    if df is not None and not df.empty:
        last_date = pd.to_datetime(df["time"].max()).date()
        if last_date >= expected:
            return df
        best_df, best_date = df, last_date

    with _cf.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fn, symbol): fn.__name__ for fn in _FALLBACK_SOURCES}
        try:
            for fut in _cf.as_completed(futures, timeout=race_timeout):
                try:
                    d = fut.result()
                except Exception:
                    continue
                if d is None or d.empty:
                    continue
                last_date = pd.to_datetime(d["time"].max()).date()
                if last_date >= expected:
                    ex.shutdown(wait=False, cancel_futures=True)
                    return d
                if best_date is None or last_date > best_date:
                    best_df, best_date = d, last_date
        except _cf.TimeoutError:
            pass
        ex.shutdown(wait=False, cancel_futures=True)

    return best_df


# ──────────────────────────────────────────────
# LẤY DANH SÁCH MÃ HOSE
# Ưu tiên: vnstock 4.x (Reference) → DNSE → FireAnt
# ──────────────────────────────────────────────
def _get_hose_tickers_vnstock() -> list:
    """
    vnstock 4.x Unified UI:
      from vnstock import Reference
      ref = Reference()
      ref.equity.list_by_exchange()   # danh sách mã theo sàn
      ref.equity.list()               # toàn bộ mã (fallback nếu list_by_exchange lỗi)
    """
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
            df = df[df[type_col].astype(str).str.upper().isin(
                ["STOCK", "CP", "CỔ PHIẾU", "EQ", "EQUITY"]
            )]

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
        url = "https://finfo-api.dnse.com.vn/v3/market-data/listing"
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
        tickers = []
        for item in items:
            if not isinstance(item, dict):
                continue
            exchange = str(item.get("exchange", item.get("floor", ""))).upper()
            if exchange not in ("HOSE", "HSX"):
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
        url = "https://api.fireant.vn/securities?type=1&exchange=HOSE&offset=0&limit=500"
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        items = r.json()
        if not isinstance(items, list):
            items = items.get("data", [])
        tickers = [
            str(i.get("symbol", i.get("ticker", ""))).strip().upper()
            for i in items if isinstance(i, dict)
        ]
        tickers = [t for t in tickers if t]
        if tickers:
            _log(f"✅ [FireAnt listing] {len(tickers)} mã HOSE")
        return tickers
    except Exception as e:
        _log_err("_get_hose_tickers_fireant", e)
        return []


def get_hose_tickers() -> list:
    """Lấy danh sách mã HOSE: vnstock (chính) → DNSE → FireAnt (dự phòng)."""
    tickers = _get_hose_tickers_vnstock()
    if tickers:
        return tickers

    _log("⚠️ vnstock listing lỗi → thử DNSE/FireAnt")
    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        f_dnse = ex.submit(_get_hose_tickers_dnse)
        f_fa   = ex.submit(_get_hose_tickers_fireant)
        tickers_dnse = f_dnse.result()
        tickers_fa   = f_fa.result()

    if tickers_dnse:
        return tickers_dnse
    if tickers_fa:
        return tickers_fa

    _log("❌ Không lấy được danh sách mã HOSE từ bất kỳ nguồn nào!")
    return []


# ──────────────────────────────────────────────
# TÍNH ĐIỂM BREADTH
# ──────────────────────────────────────────────
def compute_breadth_score(ad_pct, pct_above_ma50):
    score = round((ad_pct - 50) / 50 * 4 + (pct_above_ma50 - 50) / 50 * 4)
    return max(-8, min(8, int(score)))

def compute_momentum_note(ad_pct, pct_above_ma20, pct_above_ma50, score):
    if score >= 5:  return "🟢 Thị trường khoẻ toàn diện: đa số mã đang tăng giá và giữ trên các đường MA."
    if score >= 2:  return "🟢 Thị trường tích cực, dòng tiền lan toả ở nhiều mã."
    if score <= -5: return "🔴 Thị trường yếu diện rộng: phần lớn mã giảm giá và gãy các đường MA."
    if score <= -2: return "🟠 Thị trường suy yếu, số mã giảm giá đang chiếm ưu thế."
    return "🟡 Thị trường phân hoá / đi ngang, chưa có xu hướng rõ ràng trên diện rộng."


# ──────────────────────────────────────────────
# XỬ LÝ 1 MÃ (dùng trong ThreadPool)
# ──────────────────────────────────────────────
def _process_one(ticker: str) -> dict | None:
    df = get_price_history(ticker)
    if df is None or len(df) < MIN_LEN_FOR_MA:
        return None

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    close      = float(last["close"])
    prev_close = float(prev["close"])
    if prev_close <= 0:
        return None

    data_date = pd.to_datetime(last["time"]).strftime("%Y-%m-%d")
    chg = (close - prev_close) / prev_close * 100

    return {
        "advance":    1 if close > prev_close else 0,
        "decline":    1 if close < prev_close else 0,
        "unchanged":  1 if close == prev_close else 0,
        "above_ma20": 1 if pd.notna(last["ma20"]) and close > last["ma20"] else 0,
        "above_ma50": 1 if pd.notna(last["ma50"]) and close > last["ma50"] else 0,
        "ad_change":  chg,
        "data_date":  data_date,
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

    _log(f"📊 Bắt đầu quét {len(tickers)} mã HOSE (dữ liệu EOD, song song {MAX_WORKERS} luồng)...")

    advance = decline = unchanged = above_ma20 = above_ma50 = n_valid = 0
    ad_change_sum = 0.0
    date_counter  = Counter()
    n_errors      = 0
    done          = 0

    with _cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_map = {ex.submit(_process_one, t): t for t in tickers}
        for fut in _cf.as_completed(future_map):
            done += 1
            try:
                row = fut.result()
            except Exception:
                n_errors += 1
                row = None

            if row is None:
                n_errors += 1 if row is None and done > n_errors else 0
                continue

            advance      += row["advance"]
            decline      += row["decline"]
            unchanged    += row["unchanged"]
            above_ma20   += row["above_ma20"]
            above_ma50   += row["above_ma50"]
            ad_change_sum += row["ad_change"]
            date_counter[row["data_date"]] += 1
            n_valid += 1

            if done % 50 == 0:
                _log(f"... {done}/{len(tickers)} mã xong ({n_valid} hợp lệ, {done - n_valid} lỗi/thiếu data)")

    if n_valid == 0:
        _log("❌ Không có mã nào quét thành công — TOÀN BỘ nguồn giá đang lỗi.")
        return None

    ad_pct         = advance / n_valid * 100
    pct_above_ma20 = above_ma20 / n_valid * 100
    pct_above_ma50 = above_ma50 / n_valid * 100
    score          = compute_breadth_score(ad_pct, pct_above_ma50)
    note           = compute_momentum_note(ad_pct, pct_above_ma20, pct_above_ma50, score)
    data_date      = date_counter.most_common(1)[0][0] if date_counter else None

    result = {
        "updated_at":     _vn_now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date":      data_date,
        "n_total":        n_valid,
        "advance":        advance,
        "decline":        decline,
        "unchanged":      unchanged,
        "ad_pct":         round(ad_pct, 2),
        "pct_above_ma20": round(pct_above_ma20, 2),
        "pct_above_ma50": round(pct_above_ma50, 2),
        "breadth_score":  score,
        "momentum_note":  note,
        "ad_change":      round(ad_change_sum / n_valid, 3),
    }

    _log(
        f"✅ Xong: {n_valid}/{len(tickers)} mã hợp lệ | "
        f"A/D {advance}/{decline} ({ad_pct:.1f}%) | "
        f"MA20={pct_above_ma20:.1f}% | MA50={pct_above_ma50:.1f}% | Score={score:+d} | "
        f"data_date={data_date}"
    )
    return result


def save_to_json(result: dict, path="breadth.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    _log(f"💾 Đã ghi `{path}`.")


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

        if not force:
            mins = _minutes_since_last_update()
            if mins is not None and mins < MIN_REFRESH_MINUTES:
                _log(f"⏭️  Đã quét {mins:.0f} phút trước (< {MIN_REFRESH_MINUTES} phút) — bỏ qua.")
                sys.exit(0)

        api_key = os.environ.get("VNSTOCK_API_KEY", "").strip()
        if api_key:
            try:
                import vnai
                vnai.setup_api_key(api_key)
                set_rate_limit(55)
                _log("🔑 VNSTOCK_API_KEY truyền vào — rate limit 55/phút")
            except Exception as e:
                _log_err("setup vnai (bỏ qua)", e)
        else:
            _log("ℹ️  Không có VNSTOCK_API_KEY — dùng rate limit khách 18/phút")

        max_t  = os.environ.get("MAX_TICKERS")
        result = scan_breadth(max_tickers=int(max_t) if max_t else None)

        if result is None:
            _log("❌ Quét thất bại — không ghi file.")
            sys.exit(1)

        save_to_json(result)

    except Exception as e:
        _log(f"💥 LỖI KHÔNG LƯỜNG TRƯỚC: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
