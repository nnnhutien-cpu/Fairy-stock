"""
bulk_fetch_prices.py
=====================
Bot chạy NỀN (1 lần/ngày, sau giờ đóng cửa) để lấy sẵn dữ liệu giá lịch sử của
nhiều mã cổ phiếu và lưu vào file data/stock_prices.csv NGAY TRONG REPO.
Không dùng database ngoài nào cả (không Supabase) — GitHub Actions sẽ tự động
commit file này ngược lại vào repo sau khi chạy xong (xem
.github/workflows/bulk_fetch_prices.yml).

TẠI SAO CẦN FILE NÀY:
Tab "Bộ Lọc" trong app nếu gọi API sống cho từng mã lúc người dùng bấm nút sẽ luôn
bị giới hạn 20-60 request/phút của vnstock -> quét 500 mã tối thiểu mất vài phút,
KHÔNG THỂ nhanh xuống còn ~20 giây dù tối ưu code thế nào.
Giải pháp: chạy bot này 1 lần/ngày (không ai phải chờ), lấy sẵn dữ liệu và lưu vào
data/stock_prices.csv. Vì Streamlit Cloud luôn chạy app đúng từ code trong repo,
file này có sẵn ngay trên đĩa khi app khởi động. Khi người dùng bấm "Quét", app chỉ
ĐỌC FILE (không gọi API) -> 500 mã chỉ mất vài giây (đọc CSV + tính Ichimoku bằng pandas).

CÁCH DÙNG (chạy thủ công để test):
    python bulk_fetch_prices.py
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta

import pandas as pd
from vnstock.api.quote import Quote

# ==========================================================
# 1. CẤU HÌNH
# ==========================================================
DAYS_BACK = int(os.environ.get("BULK_FETCH_DAYS_BACK", "200"))
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stock_prices.csv")

# Hạn mức request/phút: để trống VNSTOCK_API_KEY -> dùng mức khách (18, an toàn dưới 20).
# Có API key (đăng ký miễn phí tại vnstocks.com/login) -> đặt VNSTOCK_API_KEY trong
# GitHub Secrets để tăng lên tới 55 (an toàn dưới 60) -> bot chạy nhanh hơn nhiều.
VNSTOCK_API_KEY = os.environ.get("VNSTOCK_API_KEY", "").strip()
RATE_LIMIT_PER_MIN = 55 if VNSTOCK_API_KEY else 18

if VNSTOCK_API_KEY:
    try:
        import vnai
        vnai.setup_api_key(VNSTOCK_API_KEY)
        print("🔑 Đã đăng ký API key vnstock -> hạn mức 60 request/phút.")
    except Exception as e:
        print(f"⚠️ Không đăng ký được API key vnstock ({e}), dùng hạn mức khách.")

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
# 3. CHẠY CÀO + GHI RA FILE data/stock_prices.csv
# ==========================================================
def main():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime('%Y-%m-%d')

    all_frames = []
    ok_count, fail_count = 0, 0
    print(f"⏳ Bắt đầu cào {len(PRIORITY_TICKERS)} mã (hạn mức {RATE_LIMIT_PER_MIN} req/phút)...")

    for i, ticker in enumerate(PRIORITY_TICKERS, start=1):
        df = fetch_one(ticker, start_date, end_date)
        if df is None or df.empty:
            print(f"  [{i}/{len(PRIORITY_TICKERS)}] ⚠️ {ticker}: không lấy được dữ liệu.")
            fail_count += 1
            continue

        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
        df.rename(columns={"time": "date"}, inplace=True)
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        df.insert(0, "ticker", ticker)
        all_frames.append(df)
        print(f"  [{i}/{len(PRIORITY_TICKERS)}] ✅ {ticker}: {len(df)} dòng.")
        ok_count += 1

    if not all_frames:
        print("❌ Không cào được mã nào. Dừng lại, KHÔNG ghi đè file cũ.")
        sys.exit(1)

    final_df = pd.concat(all_frames, ignore_index=True)
    final_df = final_df.sort_values(["ticker", "date"]).reset_index(drop=True)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    final_df.to_csv(OUTPUT_PATH, index=False)

    print(f"🎉 HOÀN TẤT! Thành công {ok_count} mã, lỗi {fail_count} mã.")
    print(f"📁 Đã ghi {len(final_df)} dòng vào {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
