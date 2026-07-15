"""
bulk_fetch_prices.py
=====================
Bot chạy NỀN (1 lần/ngày, sau giờ đóng cửa) để lấy sẵn dữ liệu giá lịch sử của
nhiều mã cổ phiếu và lưu vào bảng `stock_prices` trên Supabase.

TẠI SAO CẦN FILE NÀY:
Tab "Bộ Lọc" trong app nếu gọi API sống cho từng mã lúc người dùng bấm nút sẽ luôn
bị giới hạn 20-60 request/phút của vnstock -> quét 500 mã tối thiểu mất vài phút,
KHÔNG THỂ nhanh xuống còn ~20 giây dù tối ưu code thế nào.
Giải pháp: chạy bot này 1 lần/ngày (không ai phải chờ), lấy sẵn dữ liệu và lưu vào
database. Khi người dùng bấm "Quét", app chỉ ĐỌC DATABASE (không gọi API) -> 500 mã
chỉ mất vài giây (thời gian đọc DB + tính toán Ichimoku bằng pandas).

CÁCH DÙNG:
    python bulk_fetch_prices.py

CẦN THIẾT LẬP TRƯỚC:
1. Biến môi trường (hoặc GitHub Secrets) SUPABASE_URL, SUPABASE_KEY.
2. Tạo bảng `stock_prices` trên Supabase bằng SQL sau (chạy 1 lần trong SQL Editor):

    create table if not exists stock_prices (
        ticker text not null,
        date date not null,
        open double precision,
        high double precision,
        low double precision,
        close double precision,
        volume bigint,
        updated_at timestamptz default now(),
        primary key (ticker, date)
    );
    create index if not exists idx_stock_prices_ticker_date
        on stock_prices (ticker, date desc);
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta

import pandas as pd
from supabase import create_client
from vnstock.api.quote import Quote

# ==========================================================
# 1. CẤU HÌNH
# ==========================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DAYS_BACK = int(os.environ.get("BULK_FETCH_DAYS_BACK", "200"))

# Hạn mức request/phút: để trống VNSTOCK_API_KEY -> dùng mức khách (18, an toàn dưới 20).
# Có API key (đăng ký miễn phí tại vnstocks.com/login) -> đặt VNSTOCK_API_KEY trong secrets
# để tăng lên tới 55 (an toàn dưới 60) -> bot chạy nhanh hơn nhiều.
VNSTOCK_API_KEY = os.environ.get("VNSTOCK_API_KEY", "").strip()
RATE_LIMIT_PER_MIN = 55 if VNSTOCK_API_KEY else 18

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Thiếu biến môi trường SUPABASE_URL / SUPABASE_KEY. Dừng lại.")
    sys.exit(1)

if VNSTOCK_API_KEY:
    try:
        import vnai
        vnai.setup_api_key(VNSTOCK_API_KEY)
        print("🔑 Đã đăng ký API key vnstock -> hạn mức 60 request/phút.")
    except Exception as e:
        print(f"⚠️ Không đăng ký được API key vnstock ({e}), dùng hạn mức khách.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Danh sách mã cần cào. Có thể mở rộng danh sách này (vd: đọc từ get_all_tickers())
# để cào hết cả sàn, miễn là chấp nhận bot chạy lâu hơn (không ai phải chờ vì chạy nền).
PRIORITY_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "DGC", "DPM", "DCM", "PVD", "PVS", "GEX", "KDH", "NLG", "DXG", "PDR",
    "VND", "HCM", "VCI", "BSI", "CTS", "MSB", "OCB", "EIB", "LPB", "SGB",
    "REE", "GMD", "HAH", "PNJ", "DGW", "FRT", "VTP", "ANV", "VHC", "DBC",
]

# ==========================================================
# 2. TỰ GIỚI HẠN TỐC ĐỘ (giống hệt data_loader.py, để không bị vnstock tự chặn)
# ==========================================================
_rate_lock = threading.Lock()
_call_timestamps = []

def _throttle():
    with _rate_lock:
        now = time.time()
        while _call_timestamps and now - _call_timestamps[0] > 60:
            _call_timestamps.pop(0)
        if len(_call_timestamps) >= RATE_LIMIT_PER_MIN:
            wait = 60 - (now - _call_timestamps[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _call_timestamps and now - _call_timestamps[0] > 60:
                _call_timestamps.pop(0)
        _call_timestamps.append(now)

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

def fetch_one(ticker, start, end):
    for src in ['VCI', 'MSN']:
        try:
            _throttle()
            df = Quote(symbol=ticker, source=src).history(start=start, end=end, interval='1D')
            if df is not None and not df.empty:
                return _normalize(df)
        except Exception:
            continue
    return pd.DataFrame()

# ==========================================================
# 3. CHẠY CÀO + BƠM VÀO SUPABASE
# ==========================================================
def main():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime('%Y-%m-%d')

    ok_count, fail_count = 0, 0
    print(f"⏳ Bắt đầu cào {len(PRIORITY_TICKERS)} mã (hạn mức {RATE_LIMIT_PER_MIN} req/phút)...")

    for i, ticker in enumerate(PRIORITY_TICKERS, start=1):
        df = fetch_one(ticker, start_date, end_date)
        if df is None or df.empty:
            print(f"  [{i}/{len(PRIORITY_TICKERS)}] ⚠️ {ticker}: không lấy được dữ liệu.")
            fail_count += 1
            continue

        records = [
            {
                "ticker": ticker,
                "date": row["time"].strftime("%Y-%m-%d"),
                "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                "close": float(row["close"]) if pd.notna(row.get("close")) else None,
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
            }
            for _, row in df.iterrows()
        ]

        try:
            # Upsert theo khoá (ticker, date): ghi đè nếu trùng, thêm mới nếu chưa có.
            supabase.table("stock_prices").upsert(records, on_conflict="ticker,date").execute()
            print(f"  [{i}/{len(PRIORITY_TICKERS)}] ✅ {ticker}: đã lưu {len(records)} dòng.")
            ok_count += 1
        except Exception as e:
            print(f"  [{i}/{len(PRIORITY_TICKERS)}] ❌ {ticker}: lỗi lưu Supabase -> {e}")
            fail_count += 1

    print(f"🎉 HOÀN TẤT! Thành công {ok_count} mã, lỗi {fail_count} mã.")
    if ok_count == 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
