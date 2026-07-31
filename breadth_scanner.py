"""
breadth_scanner.py
==================
Script CHẠY NỀN (không phụ thuộc Streamlit) để quét ~400 mã sàn HOSE, tính các
chỉ số "sức khỏe thị trường" (market breadth) rồi ghi kết quả vào bảng
Supabase `market_breadth`. App (market_breadth.py -> get_market_breadth())
chỉ ĐỌC bảng này, không tự quét khi người dùng mở dashboard.

Chạy thủ công:
    python breadth_scanner.py

Chạy tự động: xem .github/workflows/scan_breadth.yml
(trigger bằng tay qua GitHub -> Actions -> Scan Breadth HOSE -> Run workflow,
hoặc theo lịch cron đã cấu hình sẵn).

Yêu cầu biến môi trường:
    SUPABASE_URL, SUPABASE_KEY   (bắt buộc, để ghi kết quả)
    VNSTOCK_API_KEY              (tuỳ chọn, để tăng tốc độ quét)
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone, timedelta

import pandas as pd

# ==========================================================
# CẤU HÌNH
# ==========================================================
MIN_LEN_FOR_MA = 55          # cần ít nhất 55 phiên để tính MA50 an toàn
MAX_WORKERS = 4              # giống giới hạn kết nối đồng thời của vnstock khách
DEFAULT_RATE_LIMIT_PER_MIN = 18

VN_TZ = timezone(timedelta(hours=7))

# Không quét lại nếu lần quét trước cách đây chưa tới ngần này phút — tránh
# quét trùng lặp lãng phí API khi lịch cron (chạy dày để tăng cơ hội không bị
# GitHub bỏ lượt) vô tình kích hoạt liên tiếp gần nhau.
MIN_REFRESH_MINUTES = 25


def _is_trading_window(now_vn: datetime) -> bool:
    """Phiên sáng 9h00-11h30, phiên chiều 13h00-15h50 (giờ VN), Thứ 2 - Thứ 6."""
    if now_vn.weekday() >= 5:
        return False
    t = now_vn.time()
    morning   = datetime.strptime("09:00", "%H:%M").time() <= t <= datetime.strptime("11:30", "%H:%M").time()
    afternoon = datetime.strptime("13:00", "%H:%M").time() <= t <= datetime.strptime("15:50", "%H:%M").time()
    return morning or afternoon


def _minutes_since_last_update(path="breadth.json"):
    """Đọc breadth.json hiện có (nếu có) để biết lần quét trước cách đây bao lâu."""
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last = datetime.strptime(data["updated_at"], "%Y-%m-%d %H:%M:%S")
        now = datetime.now(VN_TZ).replace(tzinfo=None)
        return (now - last).total_seconds() / 60
    except Exception:
        return None  # chưa có file / lỗi đọc -> coi như chưa từng quét


def _log(msg):
    print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] {msg}", flush=True)


# ==========================================================
# RATE LIMIT (rải đều request, không để vnstock tự block rồi retry ngầm)
# ==========================================================
_rate_lock = threading.Lock()
_call_timestamps = []
_rate_limit_per_min = DEFAULT_RATE_LIMIT_PER_MIN


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


# ==========================================================
# LẤY DANH SÁCH MÃ HOSE
# ==========================================================
def get_hose_tickers():
    from vnstock.api.listing import Listing

    for src in ['vci', 'kbs']:
        try:
            _throttle()
            df = Listing(source=src).symbols_by_exchange()
            df.columns = [str(c).lower().strip() for c in df.columns]

            type_col = next((c for c in df.columns if 'type' in c), None)
            if type_col:
                df = df[df[type_col].astype(str).str.upper().isin(['STOCK', 'CP', 'CỔ PHIẾU'])]

            if 'exchange' in df.columns:
                df = df[df['exchange'].astype(str).str.upper().isin(['HOSE', 'HSX'])]

            col = 'symbol' if 'symbol' in df.columns else ('ticker' if 'ticker' in df.columns else None)
            if col:
                tickers = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
                if tickers:
                    return tickers
        except Exception as e:
            _log(f"⚠️ Lỗi lấy danh sách mã từ nguồn {src}: {e}")
            continue

    return []


# ==========================================================
# LẤY DỮ LIỆU GIÁ 1 MÃ (60 phiên gần nhất là đủ cho MA50)
# ==========================================================
def _expected_latest_trading_date(now_vn: datetime = None):
    """
    Ngày giao dịch GẦN NHẤT mà dữ liệu đóng cửa lẽ ra phải sẵn sàng — cùng quy
    tắc với data_loader.py: đóng cửa 15h, dữ liệu sẵn sàng chậm nhất 17h.
    """
    if now_vn is None:
        now_vn = datetime.now(VN_TZ)
    d = now_vn.date()
    if now_vn.weekday() < 5 and now_vn.time() < datetime.strptime("17:00", "%H:%M").time():
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def get_price_history(ticker, days_back=120):
    from vnstock.api.quote import Quote

    end_date = datetime.now(VN_TZ).strftime('%Y-%m-%d')
    start_date = (datetime.now(VN_TZ) - pd.Timedelta(days=days_back)).strftime('%Y-%m-%d')
    # Không dừng lại ở nguồn đầu tiên "không rỗng" — nếu VCI bị chậm 1 phiên,
    # thử tiếp MSN xem có bản mới hơn không (giống lỗi đã sửa ở data_loader.py).
    expected_date = _expected_latest_trading_date()
    best_df, best_last_date = None, None

    for src in ['VCI', 'MSN']:
        try:
            _throttle()
            df = Quote(symbol=ticker, source=src).history(
                start=start_date, end=end_date, interval='1D'
            )
            if df is not None and not df.empty:
                df.columns = [str(c).lower().strip() for c in df.columns]
                if 'date' in df.columns and 'time' not in df.columns:
                    df = df.rename(columns={'date': 'time'})
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                df = df.dropna(subset=['close']).sort_values('time').reset_index(drop=True)
                if df.empty:
                    continue
                last_date = pd.to_datetime(df['time'].max()).date()
                if last_date >= expected_date:
                    return df  # đủ mới -> dùng luôn, không cần thử nguồn kia
                if best_last_date is None or last_date > best_last_date:
                    best_df, best_last_date = df, last_date
        except Exception:
            continue
    return best_df


# ==========================================================
# TÍNH BREADTH SCORE (-8 .. +8) TỪ A/D% VÀ % MÃ TRÊN MA50
# ==========================================================
def compute_breadth_score(ad_pct, pct_above_ma50):
    score_ad = (ad_pct - 50) / 50 * 4        # -4 .. +4
    score_ma = (pct_above_ma50 - 50) / 50 * 4  # -4 .. +4
    total = round(score_ad + score_ma)
    return max(-8, min(8, int(total)))


def compute_momentum_note(ad_pct, pct_above_ma20, pct_above_ma50, breadth_score):
    if breadth_score >= 5:
        return "🟢 Thị trường khoẻ toàn diện: đa số mã đang tăng giá và giữ trên các đường MA."
    if breadth_score >= 2:
        return "🟢 Thị trường tích cực, dòng tiền lan toả ở nhiều mã."
    if breadth_score <= -5:
        return "🔴 Thị trường yếu diện rộng: phần lớn mã giảm giá và gãy các đường MA."
    if breadth_score <= -2:
        return "🟠 Thị trường suy yếu, số mã giảm giá đang chiếm ưu thế."
    return "🟡 Thị trường phân hoá / đi ngang, chưa có xu hướng rõ ràng trên diện rộng."


# ==========================================================
# QUÉT TOÀN BỘ
# ==========================================================
def scan_breadth(max_tickers=None):
    tickers = get_hose_tickers()
    if not tickers:
        _log("❌ Không lấy được danh sách mã HOSE. Dừng quét.")
        return None

    if max_tickers:
        tickers = tickers[:max_tickers]

    _log(f"📊 Bắt đầu quét {len(tickers)} mã HOSE...")

    advance = decline = unchanged = 0
    above_ma20 = above_ma50 = 0
    n_valid = 0
    ad_change_sum = 0.0
    from collections import Counter
    data_date_counter = Counter()

    for i, ticker in enumerate(tickers, start=1):
        df = get_price_history(ticker)
        if df is None or len(df) < MIN_LEN_FOR_MA:
            continue

        df['ma20'] = df['close'].rolling(20).mean()
        df['ma50'] = df['close'].rolling(50).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        close = float(last['close'])
        prev_close = float(prev['close'])
        if prev_close <= 0:
            continue

        data_date_counter[pd.to_datetime(last['time']).strftime('%Y-%m-%d')] += 1
        chg_pct = (close - prev_close) / prev_close * 100
        ad_change_sum += chg_pct

        if close > prev_close:
            advance += 1
        elif close < prev_close:
            decline += 1
        else:
            unchanged += 1

        if pd.notna(last['ma20']) and close > last['ma20']:
            above_ma20 += 1
        if pd.notna(last['ma50']) and close > last['ma50']:
            above_ma50 += 1

        n_valid += 1

        if i % 50 == 0:
            _log(f"... đã xử lý {i}/{len(tickers)} mã ({n_valid} hợp lệ)")

    if n_valid == 0:
        _log("❌ Không có mã nào quét thành công. Dừng.")
        return None

    ad_pct = advance / n_valid * 100
    pct_above_ma20 = above_ma20 / n_valid * 100
    pct_above_ma50 = above_ma50 / n_valid * 100
    breadth_score = compute_breadth_score(ad_pct, pct_above_ma50)
    momentum_note = compute_momentum_note(ad_pct, pct_above_ma20, pct_above_ma50, breadth_score)
    ad_change_avg = ad_change_sum / n_valid
    # Ngày phiên mà ĐA SỐ mã đang có dữ liệu (khác với updated_at = lúc script
    # chạy) — dùng để UI cảnh báo nếu breadth đang tính trên giá bị chậm phiên.
    data_date = data_date_counter.most_common(1)[0][0] if data_date_counter else None

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
        "breadth_score":  breadth_score,
        "momentum_note":  momentum_note,
        "ad_change":      round(ad_change_avg, 3),
    }

    _log(f"✅ Quét xong: {n_valid} mã hợp lệ | A/D {advance}/{decline} "
         f"({ad_pct:.1f}%) | %MA20={pct_above_ma20:.1f}% | %MA50={pct_above_ma50:.1f}% "
         f"| Score={breadth_score:+d}")

    return result


# ==========================================================
# GHI KẾT QUẢ RA FILE breadth.json (để workflow commit thẳng vào repo,
# KHÔNG cần Supabase / secrets gì thêm — app đọc file này qua raw.githubusercontent.com)
# ==========================================================
def save_to_json(result: dict, path="breadth.json"):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    _log(f"💾 Đã ghi kết quả vào file `{path}`.")


if __name__ == "__main__":
    force = os.environ.get("FORCE_SCAN", "").strip().lower() in ("1", "true", "yes")
    now_vn = datetime.now(VN_TZ)

    if not force and not _is_trading_window(now_vn):
        _log(f"⏭️  Ngoài giờ giao dịch ({now_vn:%H:%M} giờ VN) — bỏ qua lượt quét này.")
        sys.exit(0)

    if not force:
        mins = _minutes_since_last_update()
        if mins is not None and mins < MIN_REFRESH_MINUTES:
            _log(f"⏭️  Đã quét cách đây {mins:.0f} phút (< {MIN_REFRESH_MINUTES} phút) — bỏ qua, tránh quét trùng lặp.")
            sys.exit(0)

    active_key = os.environ.get("VNSTOCK_API_KEY", "").strip()
    if active_key:
        try:
            import vnai
            vnai.setup_api_key(active_key)
            _rate_limit_per_min = 55
        except Exception:
            pass

    max_tickers_env = os.environ.get("MAX_TICKERS")
    max_tickers = int(max_tickers_env) if max_tickers_env else None

    result = scan_breadth(max_tickers=max_tickers)
    if result is None:
        sys.exit(1)

    save_to_json(result)
