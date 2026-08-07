"""
Cập nhật hàng ngày: chỉ lấy ~5 phiên gần nhất (đủ bù các ngày lễ/nghỉ bất ngờ)
cho toàn bộ mã, upsert vào Supabase. Chạy nhanh hơn nhiều so với backfill vì
mỗi mã chỉ cần vài dòng, không phải 400 phiên.

Lên lịch chạy ~17:30 giờ VN mỗi ngày làm việc (sau khi dữ liệu đóng cửa đã có,
theo đúng logic get_expected_latest_trading_date trong data_loader.py).

CÁCH DÙNG:
    export SUPABASE_URL="https://xxxx.supabase.co"
    export SUPABASE_KEY="xxxxx"
    python daily_update.py
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
from supabase import create_client

try:
    from vnstock.api.quote import Quote
    from vnstock.api.listing import Listing
except ImportError:
    print("❌ Chưa cài vnstock: pip install vnstock")
    sys.exit(1)

DAYS_BACK = 7  # đủ bù nghỉ lễ dài, upsert sẽ tự ghi đè trùng ngày nên an toàn
RATE_LIMIT_PER_MIN = 18

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Thiếu SUPABASE_URL / SUPABASE_KEY.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

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
                    return lst
        except Exception:
            continue
    return []


def fetch_recent(ticker, start, end):
    for src in ["VCI", "MSN"]:
        try:
            throttle()
            df = Quote(symbol=ticker, source=src).history(start=start, end=end, interval="1D")
            df = normalize(df)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def upsert_ticker_data(ticker, df):
    if df.empty:
        return 0
    records = [{
        "ticker": ticker,
        "date": row["time"].strftime("%Y-%m-%d"),
        "open": float(row["open"]) if pd.notna(row["open"]) else None,
        "high": float(row["high"]) if pd.notna(row["high"]) else None,
        "low": float(row["low"]) if pd.notna(row["low"]) else None,
        "close": float(row["close"]) if pd.notna(row["close"]) else None,
        "volume": int(row["volume"]) if pd.notna(row["volume"]) else None,
    } for _, row in df.iterrows()]
    sb.table("stock_prices").upsert(records, on_conflict="ticker,date").execute()
    return len(records)


def main():
    tickers = get_all_tickers()
    if not tickers:
        print("❌ Không lấy được danh sách mã, dừng.")
        sys.exit(1)

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")

    ok, fail = 0, 0
    t0 = time.time()
    for idx, ticker in enumerate(tickers, 1):
        df = fetch_recent(ticker, start_date, end_date)
        if df.empty:
            fail += 1
            continue
        upsert_ticker_data(ticker, df)
        ok += 1
        if idx % 100 == 0:
            print(f"... {idx}/{len(tickers)} mã, {time.time()-t0:.0f}s")

    print(f"🎉 Xong: {ok} mã cập nhật, {fail} mã lỗi/rỗng, tổng {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
