"""
Backfill 1 lần: nạp lịch sử giá (mặc định 400 phiên gần nhất, đủ dư cho
Knife129 rolling window 129 + margin) cho TOÀN BỘ mã HOSE/HNX/UPCOM vào Supabase.

Chạy độc lập (KHÔNG cần streamlit đang chạy), phù hợp chạy 1 lần trên máy
local hoặc server trước khi bật cron cập nhật hàng ngày (daily_update.py).

CÁCH DÙNG:
    export SUPABASE_URL="https://xxxx.supabase.co"
    export SUPABASE_KEY="xxxxx"   # service_role key (không phải anon key,
                                   # vì cần quyền insert/upsert)
    pip install vnstock supabase pandas pytz
    python backfill_supabase.py

Có resume: nếu bị ngắt giữa chừng (mất mạng, rate limit, Ctrl+C...), chạy lại
lệnh y hệt — script sẽ tự bỏ qua các mã đã hoàn thành (đọc từ backfill_progress.txt).
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta

import pandas as pd
from supabase import create_client

try:
    from vnstock.api.quote import Quote
    from vnstock.api.listing import Listing
except ImportError:
    print("❌ Chưa cài vnstock: pip install vnstock")
    sys.exit(1)

# ==========================================================
# CẤU HÌNH
# ==========================================================
DAYS_BACK = 400          # đủ dư cho Knife129 (window 129) + margin tính rolling
RATE_LIMIT_PER_MIN = 18  # số request/phút, giữ như ngưỡng trong data_loader.py
PROGRESS_FILE = "backfill_progress.txt"
LOG_FILE = "backfill_errors.log"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Thiếu biến môi trường SUPABASE_URL / SUPABASE_KEY.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]


# ==========================================================
# LẤY DANH SÁCH 1498 MÃ (HOSE + HNX + UPCOM)
# ==========================================================
def get_all_tickers():
    for src in ["vci", "kbs"]:
        try:
            df = Listing(source=src).symbols_by_exchange()
            df.columns = [str(c).lower().strip() for c in df.columns]

            type_col = next((c for c in df.columns if "type" in c), None)
            if type_col:
                df = df[df[type_col].astype(str).str.upper().isin(["STOCK", "CP", "CỔ PHIẾU"])]

            if "exchange" in df.columns:
                df = df[df["exchange"].astype(str).str.upper().isin(["HOSE", "HSX", "HNX", "UPCOM"])]

            col = "symbol" if "symbol" in df.columns else ("ticker" if "ticker" in df.columns else None)
            if col:
                lst = sorted({str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()})
                if lst:
                    print(f"✅ Lấy danh sách mã từ nguồn '{src}': {len(lst)} mã")
                    return lst
        except Exception as e:
            print(f"⚠️ Nguồn '{src}' lỗi: {e}")
            continue

    print("⚠️ Không lấy được danh sách từ vnstock, dùng fallback (10 mã).")
    return FALLBACK_TICKERS


# ==========================================================
# THROTTLE ĐƠN GIẢN
# ==========================================================
_call_timestamps = []


def throttle():
    now = time.time()
    while _call_timestamps and now - _call_timestamps[0] > 60:
        _call_timestamps.pop(0)
    if len(_call_timestamps) >= RATE_LIMIT_PER_MIN:
        wait = 60 - (now - _call_timestamps[0]) + 0.1
        if wait > 0:
            time.sleep(wait)
    _call_timestamps.append(time.time())


def normalize(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if "date" in df.columns and "time" not in df.columns:
        df.rename(columns={"date": "time"}, inplace=True)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        if getattr(df["time"].dt, "tz", None) is not None:
            df["time"] = df["time"].dt.tz_localize(None)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "time" in df.columns:
        df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def fetch_history(ticker, start, end):
    """Thử VCI rồi MSN, trả về df đã normalize."""
    for src in ["VCI", "MSN"]:
        try:
            throttle()
            df = Quote(symbol=ticker, source=src).history(start=start, end=end, interval="1D")
            df = normalize(df)
            if not df.empty:
                return df, None
        except Exception as e:
            last_err = f"{src}: {type(e).__name__}: {e}"
            continue
    return pd.DataFrame(), locals().get("last_err", "không rõ lỗi")


# ==========================================================
# UPSERT VÀO SUPABASE
# ==========================================================
def upsert_ticker_data(ticker, df):
    if df.empty:
        return 0
    records = []
    for _, row in df.iterrows():
        records.append({
            "ticker": ticker,
            "date": row["time"].strftime("%Y-%m-%d"),
            "open": float(row["open"]) if pd.notna(row["open"]) else None,
            "high": float(row["high"]) if pd.notna(row["high"]) else None,
            "low": float(row["low"]) if pd.notna(row["low"]) else None,
            "close": float(row["close"]) if pd.notna(row["close"]) else None,
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else None,
        })
    # Chunk 500 dòng / lần để tránh payload quá lớn
    for i in range(0, len(records), 500):
        chunk = records[i:i + 500]
        sb.table("stock_prices").upsert(chunk, on_conflict="ticker,date").execute()
    return len(records)


# ==========================================================
# PROGRESS (RESUME)
# ==========================================================
# Kiểm tra TỪNG mã trực tiếp trên Supabase (dùng index ticker,date nên rất
# nhanh, <50ms/mã) thay vì chỉ dựa vào file cục bộ — vì trên GitHub Actions
# mỗi lần chạy là 1 máy ảo mới, file backfill_progress.txt không giữ được
# giữa các lần chạy. Nhờ vậy rerun (do timeout/lỗi mạng) không phải nạp lại
# từ đầu các mã đã xong.
MIN_ROWS_CONSIDERED_DONE = 200  # ít nhất ~200 phiên coi như mã đã backfill xong


def already_done_in_supabase(ticker: str) -> bool:
    try:
        resp = (
            sb.table("stock_prices")
            .select("id", count="exact")
            .eq("ticker", ticker)
            .execute()
        )
        return (resp.count or 0) >= MIN_ROWS_CONSIDERED_DONE
    except Exception:
        return False


def load_done():
    done = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            done |= set(line.strip() for line in f if line.strip())
    return done


def mark_done(ticker):
    with open(PROGRESS_FILE, "a") as f:
        f.write(ticker + "\n")


def log_error(ticker, msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {ticker} | {msg}\n")


# ==========================================================
# MAIN
# ==========================================================
def main():
    tickers = get_all_tickers()
    done = load_done()
    todo = [t for t in tickers if t not in done]

    print(f"📋 Tổng {len(tickers)} mã, đã xong {len(done)}, còn lại {len(todo)}")
    if not todo:
        print("✅ Đã backfill xong toàn bộ.")
        return

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")

    t_start = time.time()
    for idx, ticker in enumerate(todo, 1):
        if already_done_in_supabase(ticker):
            print(f"[{idx}/{len(todo)}] ⏭️  {ticker}: đã có đủ dữ liệu trên Supabase, bỏ qua")
            mark_done(ticker)
            continue

        df, err = fetch_history(ticker, start_date, end_date)
        if df.empty:
            print(f"[{idx}/{len(todo)}] ⚠️ {ticker}: rỗng ({err})")
            log_error(ticker, err or "rỗng")
            # Vẫn đánh dấu done để không lặp lại mãi nếu mã bị delist/lỗi vĩnh viễn.
            # Nếu muốn thử lại các mã lỗi sau, xoá dòng tương ứng khỏi backfill_progress.txt
            mark_done(ticker)
            continue

        n = upsert_ticker_data(ticker, df)
        mark_done(ticker)
        elapsed = time.time() - t_start
        rate = idx / elapsed * 60 if elapsed > 0 else 0
        eta_min = (len(todo) - idx) / rate if rate > 0 else 0
        print(f"[{idx}/{len(todo)}] ✅ {ticker}: {n} dòng | ~{rate:.1f} mã/phút | ETA {eta_min:.0f} phút")

    print("🎉 Backfill hoàn tất.")


if __name__ == "__main__":
    main()
