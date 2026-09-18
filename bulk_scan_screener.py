"""
QUÉT TOÀN SÀN 1 LẦN -> LƯU VÀO screener_cache.xlsx
====================================================
Chạy nền (GitHub Actions, xem scan_screener.yml) sau giờ đóng cửa mỗi ngày.
App (main.py) sẽ ĐỌC file Excel này khi mở tab "Bộ Lọc" thay vì quét sống
-> hiện mã ra trong ~1 giây thay vì phải chờ vài phút quét lại từ đầu.

Cách chạy thủ công để test:
    python bulk_scan_screener.py
"""
import os
import sys
import pandas as pd
from datetime import datetime

# Cho phép import các module cùng thư mục (data_loader, indicators)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import get_all_tickers, get_stock_data, set_rate_limit
from indicators import calculate_technical_signals

CACHE_FILE = "screener_cache.xlsx"

BLACKLIST = {"BCG", "HBC", "HNG", "POM", "HAG", "ITA", "TGG", "TTB"}

# Tham số Ichimoku mặc định (khớp với default trong render_sidebar của main.py)
DEFAULT_PARAMS = dict(p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26)


def run_full_scan(exchange="all", days_back=200, params=None):
    """Quét toàn bộ mã của 1 sàn (hoặc 'all'), trả về (DataFrame kết quả, danh sách lỗi)."""
    params = params or DEFAULT_PARAMS
    tickers = get_all_tickers(exchange)
    if not tickers:
        return pd.DataFrame(), ["get_all_tickers trả về danh sách rỗng"]

    results, errors = [], []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        if ticker in BLACKLIST:
            continue
        try:
            df = get_stock_data(ticker, days_back=days_back)
            if df is None or df.empty:
                continue
            res = calculate_technical_signals(
                df, ticker,
                params["p_tenkan"], params["p_kijun"],
                params["p_senkou_b"], params["p_shift"],
            )
            if res:
                results.append(res)
        except Exception as e:
            errors.append(f"{ticker}: {e}")

        if i % 50 == 0:
            print(f"  ... đã xử lý {i}/{total} mã ({len(results)} hợp lệ, {len(errors)} lỗi)")

    return pd.DataFrame(results), errors


def main():
    # Có API key trong biến môi trường -> quét nhanh hơn (60/phút thay vì 20/phút)
    api_key = os.environ.get("VNSTOCK_API_KEY", "")
    if api_key:
        try:
            import vnai
            vnai.setup_api_key(api_key)
            set_rate_limit(55)
        except Exception:
            set_rate_limit(18)
    else:
        set_rate_limit(18)

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Bắt đầu quét toàn sàn...")
    df_result, errors = run_full_scan()

    if df_result.empty:
        print(f"❌ Quét thất bại, không có mã nào hợp lệ. Lỗi: {errors[:5]}")
        sys.exit(1)

    df_result["_scanned_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with pd.ExcelWriter(CACHE_FILE, engine="openpyxl") as writer:
        df_result.to_excel(writer, index=False, sheet_name="scan")

    print(f"✅ Đã quét xong {len(df_result)} mã hợp lệ, {len(errors)} lỗi.")
    print(f"   Đã lưu vào {CACHE_FILE} (cột _scanned_at ghi thời điểm quét).")


if __name__ == "__main__":
    main()
