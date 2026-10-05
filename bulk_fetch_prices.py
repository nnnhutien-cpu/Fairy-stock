"""
bulk_fetch_prices.py - Bot nền: lấy giá ngày từ TCBS và upsert vào Supabase `stock_prices`
(thay thế bản dùng vnstock). App Streamlit chỉ ĐỌC bảng này -> quét nhanh, không bị rate-limit.

Cách chạy:
    # Lần đầu: nạp ~420 ngày cho toàn bộ mã
    python bulk_fetch_prices.py --backfill

    # Hằng ngày (GitHub Actions): chỉ lấy 15 ngày gần nhất để bù ngày nghỉ/lễ
    python bulk_fetch_prices.py

    # Thử nhanh vài mã
    python bulk_fetch_prices.py --tickers HPG,SHS,BSR --days 30

Biến môi trường (đặt trong GitHub Secrets, KHÔNG ghi vào code):
    SUPABASE_URL, SUPABASE_KEY   (khoá cần quyền GHI - xem ghi chú trong setup_supabase.sql)
    TCBS_RATE_LIMIT              số request/phút tới TCBS, mặc định 100

Đơn vị: giá cổ phiếu lưu theo "nghìn đồng" (20.05) cho khớp app cũ; chỉnh bằng TCBS_PRICE_DIVISOR.
Không cần API key TCBS.
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd

import tcbs_client

TABLE = "stock_prices"
INDEX_SYMBOLS = ["VNINDEX", "VN30", "HNXINDEX", "UPCOM"]  # lưu thêm để app đọc được từ DB


def get_supabase():
    from supabase import create_client
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise SystemExit("Thiếu SUPABASE_URL / SUPABASE_KEY trong biến môi trường.")
    return create_client(url, key)


def to_rows(ticker, df):
    """DataFrame TCBS -> list dict đúng cột bảng stock_prices."""
    if df is None or df.empty:
        return []
    d = df.dropna(subset=["close"]).copy()
    d["date"] = pd.to_datetime(d["time"]).dt.strftime("%Y-%m-%d")
    d = d.drop_duplicates(subset="date", keep="last")
    rows = []
    for r in d.itertuples(index=False):
        rows.append({
            "ticker": ticker,
            "date": r.date,
            "open": None if pd.isna(r.open) else float(r.open),
            "high": None if pd.isna(r.high) else float(r.high),
            "low": None if pd.isna(r.low) else float(r.low),
            "close": float(r.close),
            "volume": 0 if pd.isna(r.volume) else int(r.volume),
        })
    return rows


def fetch_one(ticker, start, end):
    df = tcbs_client.history(ticker, start, end, "1D")
    return ticker, to_rows(ticker, df)


def upsert(sb, rows, batch=1000):
    for i in range(0, len(rows), batch):
        sb.table(TABLE).upsert(rows[i:i + batch], on_conflict="ticker,date").execute()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=15, help="số ngày lịch gần nhất cần lấy (mặc định 15)")
    ap.add_argument("--backfill", action="store_true", help="nạp lịch sử dài (420 ngày)")
    ap.add_argument("--tickers", type=str, default="", help="danh sách mã, ngăn cách bằng dấu phẩy")
    ap.add_argument("--exchange", type=str, default="all", help="all | HOSE | HNX | UPCOM")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="chỉ lấy dữ liệu, không ghi Supabase")
    args = ap.parse_args(argv)

    days = 420 if args.backfill else args.days
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = tcbs_client.list_symbols(args.exchange)
        if not tickers:
            raise SystemExit("Không đọc được tickers.json - hãy chạy sync_tickers.py và commit file đó.")
        if args.exchange.lower() == "all":
            tickers = INDEX_SYMBOLS + tickers

    sb = None if args.dry_run else get_supabase()
    print(f"Lấy {len(tickers)} mã, {start} -> {end}, workers={args.workers}", flush=True)

    ok, empty, failed, total_rows = 0, [], [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, t, start, end): t for t in tickers}
        for n, fut in enumerate(as_completed(futs), 1):
            t = futs[fut]
            try:
                _, rows = fut.result()
                if not rows:
                    empty.append(t)
                else:
                    if sb is not None:
                        upsert(sb, rows)
                    ok += 1
                    total_rows += len(rows)
            except Exception as e:  # lỗi 1 mã không làm hỏng cả đợt
                failed.append(f"{t}({type(e).__name__})")
            if n % 100 == 0:
                print(f"  {n}/{len(tickers)} mã, {int(time.time() - t0)}s", flush=True)

    print(f"\nXong: {ok} mã có dữ liệu ({total_rows} dòng), {len(empty)} mã rỗng, {len(failed)} mã lỗi, "
          f"{int(time.time() - t0)}s")
    if empty:
        print("Mã rỗng (có thể ngừng giao dịch/mới niêm yết):", ", ".join(empty[:50]), "..." if len(empty) > 50 else "")
    if failed:
        print("Mã lỗi:", ", ".join(failed[:50]))
    if tcbs_client.get_last_error():
        print("Lỗi TCBS gần nhất:", tcbs_client.get_last_error())
    # Chỉ báo thất bại khi gần như không lấy được gì -> GitHub Actions hiện đỏ để bạn biết
    if tickers and ok < max(1, len(tickers) * 0.5):
        sys.exit(1)


if __name__ == "__main__":
    main()
