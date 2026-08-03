"""
breadth_scanner.py — Quét sức khỏe thị trường HOSE, ghi breadth.json
Chạy qua GitHub Actions "Scan Breadth HOSE" mỗi 15 phút trong giờ giao dịch.

BẢN SỬA: thêm logging chi tiết lý do lỗi ở TẤT CẢ các except (bản cũ hầu hết
`except Exception: continue`/`pass` không in ra gì -> log GitHub Actions chỉ
hiện "không lấy được dữ liệu" chung chung, không biết vì sao, nên 3 ngày qua
không cách nào biết bot chết vì lý do gì). Không đổi logic nghiệp vụ.
"""

import os, sys, time, json, threading, traceback
from datetime import datetime, timezone, timedelta
from collections import Counter

import pandas as pd

# ──────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────
MIN_LEN_FOR_MA          = 55
MAX_WORKERS             = 4
DEFAULT_RATE_LIMIT      = 18
VN_TZ                   = timezone(timedelta(hours=7))
MIN_REFRESH_MINUTES     = 8

_rate_lim = DEFAULT_RATE_LIMIT  # biến rate-limit toàn cục, chỉnh qua set_rate_limit()


def _vn_now():
    return datetime.now(VN_TZ).replace(tzinfo=None)


def _log(msg):
    print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] {msg}", flush=True)


def _log_err(context, e):
    """In lỗi kèm traceback rút gọn — để log GitHub Actions luôn có nguyên nhân thật,
    không còn im lặng nuốt exception nữa."""
    _log(f"⚠️ [{context}] {type(e).__name__}: {e}")


def set_rate_limit(requests_per_minute: int):
    """Đặt rate limit — dùng hàm riêng thay vì `global` rải rác giữa script,
    để rõ ràng và dễ trace hơn khi debug."""
    global _rate_lim
    _rate_lim = max(1, int(requests_per_minute))


def _is_trading_window(now_vn: datetime) -> bool:
    if now_vn.weekday() >= 5:
        return False
    t = now_vn.time()
    morning   = datetime.strptime("09:00","%H:%M").time() <= t <= datetime.strptime("11:30","%H:%M").time()
    afternoon = datetime.strptime("13:00","%H:%M").time() <= t <= datetime.strptime("15:50","%H:%M").time()
    return morning or afternoon


def _minutes_since_last_update(path="breadth.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last = datetime.strptime(data["updated_at"], "%Y-%m-%d %H:%M:%S")
        return (_vn_now() - last).total_seconds() / 60
    except FileNotFoundError:
        _log("ℹ️ Chưa có breadth.json local (lần chạy đầu, hoặc checkout không lấy file này) — quét ngay.")
        return None
    except Exception as e:
        _log_err("_minutes_since_last_update", e)
        return None


# ──────────────────────────────────────────────
# RATE LIMIT
# ──────────────────────────────────────────────
_rate_lock = threading.Lock()
_call_ts   = []


def _throttle():
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
# IMPORT VNSTOCK ĐÚNG THEO PHIÊN BẢN (tự động detect 3.x vs 4.x)
# ──────────────────────────────────────────────
def _get_listing_df(src):
    """Lấy danh sách mã — tương thích vnstock 3.x và 4.x. Ghi lại lỗi của TỪNG
    cách thử, để nếu cả 3 đều fail thì biết chính xác vì sao (thay vì im lặng)."""
    errors = []

    try:
        from vnstock import Vnstock
        obj = Vnstock(source=src).stock(symbol='VNM', exchange='HOSE')
        return obj.listing.symbols_by_exchange()
    except Exception as e:
        errors.append(f"Vnstock(4.x): {type(e).__name__}: {e}")

    try:
        from vnstock import listing_companies
        return listing_companies()
    except Exception as e:
        errors.append(f"listing_companies(3.x): {type(e).__name__}: {e}")

    try:
        from vnstock.api.listing import Listing
        return Listing(source=src).symbols_by_exchange()
    except Exception as e:
        errors.append(f"Listing(api): {type(e).__name__}: {e}")

    _log(f"❌ [_get_listing_df|{src}] Cả 3 cách đều lỗi: {' | '.join(errors)}")
    return None


def _get_price_history_df(ticker, start_date, end_date, src):
    """Lấy giá lịch sử — tương thích vnstock 3.x và 4.x, log lỗi từng cách thử."""
    errors = []

    try:
        from vnstock import Vnstock
        obj = Vnstock(source=src).stock(symbol=ticker, exchange='HOSE')
        return obj.quote.history(start=start_date, end=end_date, interval='1D')
    except Exception as e:
        errors.append(f"Vnstock(4.x): {type(e).__name__}: {e}")

    try:
        from vnstock import stock_historical_data
        return stock_historical_data(ticker, start_date, end_date, '1D', 'stock', src)
    except Exception as e:
        errors.append(f"stock_historical_data(3.x): {type(e).__name__}: {e}")

    try:
        from vnstock.api.quote import Quote
        return Quote(symbol=ticker, source=src).history(
            start=start_date, end=end_date, interval='1D'
        )
    except Exception as e:
        errors.append(f"Quote(api): {type(e).__name__}: {e}")

    # Không log full mỗi mã (sẽ tràn log 400 mã) — chỉ trả None, get_price_history
    # bên ngoài sẽ tổng hợp bao nhiêu mã lỗi.
    return None, errors


# ──────────────────────────────────────────────
# LẤY DANH SÁCH MÃ HOSE
# ──────────────────────────────────────────────
def get_hose_tickers():
    for src in ['vci', 'kbs', 'tcbs']:
        try:
            _throttle()
            df = _get_listing_df(src)
            if df is None or df.empty:
                continue

            df.columns = [str(c).lower().strip() for c in df.columns]

            type_col = next((c for c in df.columns if 'type' in c), None)
            if type_col:
                df = df[df[type_col].astype(str).str.upper().isin(
                    ['STOCK', 'CP', 'CỔ PHIẾU', 'EQ', 'EQUITY']
                )]

            if 'exchange' in df.columns:
                df = df[df['exchange'].astype(str).str.upper().isin(['HOSE', 'HSX'])]

            col = next((c for c in ['symbol', 'ticker', 'code'] if c in df.columns), None)
            if col:
                tickers = [str(t).strip().upper() for t in df[col].dropna() if str(t).strip()]
                if tickers:
                    _log(f"✅ Lấy được {len(tickers)} mã HOSE từ nguồn {src}")
                    return tickers
                else:
                    _log(f"⚠️ [get_hose_tickers|{src}] Sau khi lọc type/exchange, danh sách RỖNG "
                         f"(có thể cấu trúc cột API đã đổi — cột hiện có: {list(df.columns)}).")
        except Exception as e:
            _log_err(f"get_hose_tickers|{src}", e)
            continue

    _log("❌ Không lấy được danh sách mã HOSE từ bất kỳ nguồn nào!")
    return []


# ──────────────────────────────────────────────
# LẤY GIÁ LỊCH SỬ 1 MÃ
# ──────────────────────────────────────────────
def _expected_latest_trading_date():
    now = datetime.now(VN_TZ)
    d = now.date()
    if now.weekday() < 5 and now.time() < datetime.strptime("17:00","%H:%M").time():
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def get_price_history(ticker, days_back=120, collect_errors: list = None):
    end_date   = datetime.now(VN_TZ).strftime('%Y-%m-%d')
    start_date = (datetime.now(VN_TZ) - pd.Timedelta(days=days_back)).strftime('%Y-%m-%d')
    expected   = _expected_latest_trading_date()
    best_df, best_date = None, None

    for src in ['VCI', 'MSN', 'TCBS']:
        try:
            _throttle()
            df, src_errors = _get_price_history_df(ticker, start_date, end_date, src)
            if df is None or df.empty:
                if collect_errors is not None and src_errors:
                    collect_errors.append(f"{ticker}|{src}: {' | '.join(src_errors)}")
                continue

            df.columns = [str(c).lower().strip() for c in df.columns]
            for col in ['time', 'date', 'tradingdate', 'trading_date']:
                if col in df.columns:
                    df = df.rename(columns={col: 'time'})
                    break

            if 'time' not in df.columns:
                if collect_errors is not None:
                    collect_errors.append(f"{ticker}|{src}: thiếu cột time/date sau chuẩn hoá "
                                           f"(cột hiện có: {list(df.columns)})")
                continue

            df['close'] = pd.to_numeric(df.get('close', df.get('closeprice', None)), errors='coerce')
            df = df.dropna(subset=['close']).sort_values('time').reset_index(drop=True)
            if df.empty:
                if collect_errors is not None:
                    collect_errors.append(f"{ticker}|{src}: rỗng sau khi bỏ NaN cột close")
                continue

            last_date = pd.to_datetime(df['time'].max()).date()
            if last_date >= expected:
                return df   # đủ mới → dùng luôn
            if best_date is None or last_date > best_date:
                best_df, best_date = df, last_date
        except Exception as e:
            if collect_errors is not None:
                collect_errors.append(f"{ticker}|{src}: {type(e).__name__}: {e}")
            continue

    return best_df


# ──────────────────────────────────────────────
# TÍNH TOÁN BREADTH
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
# QUÉT TOÀN BỘ
# ──────────────────────────────────────────────
def scan_breadth(max_tickers=None):
    tickers = get_hose_tickers()
    if not tickers:
        return None

    if max_tickers:
        tickers = tickers[:max_tickers]

    _log(f"📊 Bắt đầu quét {len(tickers)} mã HOSE...")
    advance = decline = unchanged = above_ma20 = above_ma50 = n_valid = 0
    ad_change_sum = 0.0
    date_counter  = Counter()
    ticker_errors = []  # gom lỗi từng mã, chỉ in tóm tắt cuối cùng thay vì spam log

    for i, ticker in enumerate(tickers, 1):
        df = get_price_history(ticker, collect_errors=ticker_errors)
        if df is None or len(df) < MIN_LEN_FOR_MA:
            continue

        df['ma20'] = df['close'].rolling(20).mean()
        df['ma50'] = df['close'].rolling(50).mean()
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        close      = float(last['close'])
        prev_close = float(prev['close'])
        if prev_close <= 0:
            continue

        date_counter[pd.to_datetime(last['time']).strftime('%Y-%m-%d')] += 1
        chg = (close - prev_close) / prev_close * 100
        ad_change_sum += chg

        if   close > prev_close: advance   += 1
        elif close < prev_close: decline   += 1
        else:                    unchanged += 1

        if pd.notna(last['ma20']) and close > last['ma20']: above_ma20 += 1
        if pd.notna(last['ma50']) and close > last['ma50']: above_ma50 += 1
        n_valid += 1

        if i % 50 == 0:
            _log(f"... {i}/{len(tickers)} mã ({n_valid} hợp lệ, {len(ticker_errors)} lỗi tích luỹ)")

    if ticker_errors:
        _log(f"⚠️ {len(ticker_errors)} lỗi khi lấy giá — 10 lỗi đầu tiên:")
        for err in ticker_errors[:10]:
            _log(f"    · {err}")

    if n_valid == 0:
        _log("❌ Không có mã nào quét thành công — TOÀN BỘ nguồn giá đang lỗi (xem log lỗi ở trên).")
        return None

    ad_pct         = advance / n_valid * 100
    pct_above_ma20 = above_ma20 / n_valid * 100
    pct_above_ma50 = above_ma50 / n_valid * 100
    score          = compute_breadth_score(ad_pct, pct_above_ma50)
    note           = compute_momentum_note(ad_pct, pct_above_ma20, pct_above_ma50, score)
    data_date      = date_counter.most_common(1)[0][0] if date_counter else None

    result = {
        "updated_at":     datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M:%S'),
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

    _log(f"✅ Xong: {n_valid} mã | A/D {advance}/{decline} ({ad_pct:.1f}%) "
         f"| MA20={pct_above_ma20:.1f}% | MA50={pct_above_ma50:.1f}% | Score={score:+d}")
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
        force  = os.environ.get("FORCE_SCAN","").strip().lower() in ("1","true","yes")
        now_vn = datetime.now(VN_TZ).replace(tzinfo=None)

        if not force and not _is_trading_window(now_vn):
            _log(f"⏭️  Ngoài giờ giao dịch ({now_vn:%H:%M}) — bỏ qua.")
            sys.exit(0)

        if not force:
            mins = _minutes_since_last_update()
            if mins is not None and mins < MIN_REFRESH_MINUTES:
                _log(f"⏭️  Đã quét {mins:.0f} phút trước (< {MIN_REFRESH_MINUTES} phút) — bỏ qua.")
                sys.exit(0)

        api_key = os.environ.get("VNSTOCK_API_KEY","").strip()
        if api_key:
            try:
                import vnai
                vnai.setup_api_key(api_key)
                set_rate_limit(55)
                _log("🔑 Dùng API key — rate limit tăng lên 55/phút")
            except Exception as e:
                _log_err("setup vnai api key (bỏ qua, dùng rate limit mặc định)", e)

        max_t = os.environ.get("MAX_TICKERS")
        result = scan_breadth(max_tickers=int(max_t) if max_t else None)

        if result is None:
            _log("❌ Quét thất bại — không ghi file.")
            sys.exit(1)

        save_to_json(result)

    except Exception as e:
        # ✅ Bắt TẤT CẢ lỗi không lường trước ở tầng ngoài cùng — trước đây nếu
        # có exception nào lọt ra ngoài mọi try/except bên trong, workflow sẽ
        # crash với traceback khó đọc và không rõ bước nào gây ra. Giờ luôn in
        # traceback đầy đủ + thoát mã lỗi rõ ràng để Actions hiện đúng nguyên nhân.
        _log(f"💥 LỖI KHÔNG LƯỜNG TRƯỚC: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
