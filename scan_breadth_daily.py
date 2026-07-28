"""
scan_breadth_daily.py
Cào dữ liệu ~400 mã sàn HOSE, tính chỉ số Breadth (A/D%, %>MA20, %>MA50),
lưu ra breadth_latest.json + breadth_history.json để app Streamlit đọc
qua GitHub raw (giống cơ chế reports.json đã có trong app.py).

Chạy bằng GitHub Actions (xem .github/workflows/scan_breadth.yml), 1-2
lần/ngày. KHÔNG chạy trực tiếp trong app Streamlit — quét 400 mã tốn vài
phút và dễ bị rate-limit nếu nhiều người dùng cùng bấm cùng lúc.

Yêu cầu: file này đặt cùng thư mục với data_loader.py và breadth_score.py
trong repo của bạn (cùng chỗ với reports.json / app.py).
"""

import json
import time
import concurrent.futures
from datetime import datetime
from pathlib import Path

import pandas as pd

from data_loader import get_stock_data, get_all_tickers, set_rate_limit
from breadth_score import compute_breadth_metrics, breadth_momentum_note

OUTPUT_LATEST = Path("breadth_latest.json")
OUTPUT_HISTORY = Path("breadth_history.json")
MAX_HISTORY_DAYS = 90
MAX_WORKERS = 4
MIN_BARS_REQUIRED = 51  # cần >= 51 phiên để tính MA50 ổn định


def _process_ticker(ticker: str):
    try:
        df = get_stock_data(ticker, days_back=80)
        if df is None or df.empty or len(df) < MIN_BARS_REQUIRED:
            return None

        df.columns = [str(c).lower().strip() for c in df.columns]
        if "time" in df.columns:
            df = df.sort_values("time")

        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(closes) < MIN_BARS_REQUIRED:
            return None

        last_close = closes.iloc[-1]
        prev_close = closes.iloc[-2]
        change_pct = (last_close - prev_close) / prev_close * 100 if prev_close else 0

        ma20 = closes.tail(20).mean()
        ma50 = closes.tail(50).mean()

        return {
            "ticker": ticker,
            "change_pct": float(change_pct),
            "above_ma20": bool(last_close > ma20),
            "above_ma50": bool(last_close > ma50),
        }
    except Exception:
        # Bỏ qua mã lỗi (delisted, thiếu dữ liệu, v.v.) — không làm gãy cả job
        return None


def scan_all_hose(max_workers: int = MAX_WORKERS) -> pd.DataFrame:
    tickers = get_all_tickers("HOSE")
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_ticker, t): t for t in tickers}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res is not None:
                rows.append(res)
    return pd.DataFrame(rows), len(tickers)


def main():
    # Nên set VNSTOCK_API_KEY trong GitHub Secrets để quét nhanh + ổn định hơn.
    import os
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

    start = time.time()
    df, n_target = scan_all_hose()

    metrics = compute_breadth_metrics(df)
    metrics["date"] = datetime.now().strftime("%Y-%m-%d")
    metrics["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metrics["scan_seconds"] = round(time.time() - start, 1)
    metrics["n_tickers_target"] = n_target

    # --- cập nhật history (giữ tối đa MAX_HISTORY_DAYS ngày, 1 dòng/ngày, ghi đè nếu chạy 2 lần/ngày) ---
    history = []
    if OUTPUT_HISTORY.exists():
        history = json.loads(OUTPUT_HISTORY.read_text(encoding="utf-8"))

    history = [h for h in history if h.get("date") != metrics["date"]]
    history.append(metrics)
    history = history[-MAX_HISTORY_DAYS:]

    metrics["momentum_note"] = breadth_momentum_note(history)

    OUTPUT_LATEST.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"✅ Xong. {metrics['n_total']}/{metrics['n_tickers_target']} mã hợp lệ | "
        f"A/D={metrics['ad_pct']}% | %>MA50={metrics['pct_above_ma50']}% | "
        f"Breadth Score={metrics['breadth_score']:+d} | {metrics['scan_seconds']}s"
    )


if __name__ == "__main__":
    main()
