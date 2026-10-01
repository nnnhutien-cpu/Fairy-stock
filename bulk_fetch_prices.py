"""
Bot bơm giá cổ phiếu (bản mới, không dùng vnstock).

- Nguồn: tcbs_data (TCBS) + DNSE, lấy bản nào MỚI hơn.
- Đọc data/stock_prices.csv cũ, chỉ tải phần thiếu rồi gộp (không mất lịch sử).
- Mã nào có < MIN_ROWS phiên thì tải lại đủ HISTORY_DAYS ngày.
- FORCE_REBUILD=1: bỏ qua lịch sử cũ, tải lại TOÀN BỘ từ TCBS/DNSE (không cần xoá file tay).
- UNIVERSE=hose: lấy toàn bộ mã HOSE (VNDirect listing) thay vì chỉ các mã đang có trong CSV.
- Nếu SUPABASE_URL + SUPABASE_KEY có trong môi trường: upsert thêm lên bảng stock_prices.
- THOÁT MÃ LỖI (job báo đỏ) nếu dữ liệu vẫn cũ hơn phiên kỳ vọng -> không còn 'xanh giả'.
"""
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import tcbs_data

CSV_PATH = "data/stock_prices.csv"
HISTORY_DAYS = 400          # ngày lịch -> khoảng 270 phiên
MIN_ROWS = 250              # ít hơn số này thì tải lại toàn bộ lịch sử
OVERLAP_DAYS = 7            # tải chồng lên vài ngày cuối để sửa nến dở dang
SLEEP_BETWEEN = 0.4

PRIORITY_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "DGC", "DPM", "DCM", "PVD", "PVS", "GEX", "KDH", "NLG", "DXG", "PDR",
    "VND", "HCM", "VCI", "BSI", "CTS", "MSB", "OCB", "EIB", "LPB", "SGB",
    "REE", "GMD", "HAH", "PNJ", "DGW", "FRT", "VTP", "ANV", "VHC", "DBC",
]
COLS = ["ticker", "date", "open", "high", "low", "close", "volume"]


def vn_now():
    return datetime.utcnow() + timedelta(hours=7)


def expected_latest_date(now=None):
    """Phiên gần nhất lẽ ra đã có dữ liệu (sau 17:00 giờ VN thì là hôm nay). Bỏ qua ngày lễ."""
    now = now or vn_now()
    d = now.date()
    if now.weekday() < 5 and now.hour < 17:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _std(df):
    """Chuẩn hoá về cột time/open/high/low/close/volume, bỏ timezone."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    for alt in ("date", "tradingdate"):
        if alt in df.columns and "time" not in df.columns:
            df = df.rename(columns={alt: "time"})
    if "time" not in df.columns:
        return pd.DataFrame()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    if getattr(df["time"].dt, "tz", None) is not None:
        df["time"] = df["time"].dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
    return df


def fetch_tcbs(symbol, start, end):
    # +1 ngày vì nhiều API coi `end` là mốc loại trừ -> mất nến hôm nay
    end_incl = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    return _std(tcbs_data.fetch_bars_range(symbol, start, end_incl, "D"))


def fetch_dnse(symbol, start, end):
    t0 = int(datetime.strptime(start, "%Y-%m-%d").timestamp())
    t1 = int((datetime.strptime(end, "%Y-%m-%d") + timedelta(days=2)).timestamp())
    r = requests.get(
        "https://services.entrade.com.vn/chart/history",
        params={"symbol": symbol.upper(), "resolution": "D", "from": t0, "to": t1},
        timeout=15,
    )
    data = r.json()
    if data.get("s") != "ok" or not data.get("t"):
        return pd.DataFrame()
    df = pd.DataFrame({
        "time": pd.to_datetime(data["t"], unit="s"),
        "open": data["o"], "high": data["h"], "low": data["l"],
        "close": data["c"], "volume": data["v"],
    })
    return _std(df)


def fetch_best(symbol, start, end):
    """Thử cả TCBS và DNSE, lấy bản có nến mới nhất (hoà thì lấy bản nhiều dòng hơn)."""
    best, best_key = pd.DataFrame(), None
    for name, fn in (("TCBS", fetch_tcbs), ("DNSE", fetch_dnse)):
        try:
            df = fn(symbol, start, end)
            if df is None or df.empty:
                continue
            df = _std(tcbs_data.scale_to_thousand(df, symbol))
            if df.empty:
                continue
            key = (df["time"].max(), len(df))
            if best_key is None or key > best_key:
                best, best_key = df, key
        except Exception as e:
            print(f"   ! {symbol} {name}: {type(e).__name__}: {e}")
    return best


def to_rows(symbol, df):
    out = df[["time", "open", "high", "low", "close", "volume"]].copy()
    out["date"] = out["time"].dt.strftime("%Y-%m-%d")
    out["ticker"] = symbol
    return out[COLS]


def hose_tickers():
    try:
        r = requests.get(
            "https://finfo-api.vndirect.com.vn/v4/stocks",
            params={"q": "type:STOCK~status:LISTED", "fields": "code,floor", "size": 3000},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("data") or []
        lst = [str(i.get("code", "")).strip().upper() for i in items
               if str(i.get("floor", "")).upper() == "HOSE"]
        return [t for t in lst if t]
    except Exception as e:
        print(f"Không lấy được danh sách HOSE: {e}")
        return []


def load_existing():
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH)
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            return df[COLS]
        except Exception as e:
            print(f"Không đọc được {CSV_PATH}: {e}")
    return pd.DataFrame(columns=COLS)


def upsert_supabase(rows):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("(Bỏ qua Supabase: chưa có SUPABASE_URL / SUPABASE_KEY)")
        return
    try:
        from supabase import create_client
        sb = create_client(url, key)
        recs = rows.where(pd.notna(rows), None).to_dict("records")
        for i in range(0, len(recs), 500):
            sb.table("stock_prices").upsert(recs[i:i + 500], on_conflict="ticker,date").execute()
        print(f"Supabase: đã upsert {len(recs)} dòng.")
    except Exception as e:
        print(f"!! Supabase upsert lỗi (CSV vẫn đã ghi): {type(e).__name__}: {e}")


def main():
    now = vn_now()
    today = now.strftime("%Y-%m-%d")
    existing = load_existing()
    rebuild = os.environ.get("FORCE_REBUILD", "0") == "1"
    universe = os.environ.get("UNIVERSE", "existing").lower()
    tickers = sorted(existing["ticker"].unique().tolist()) or list(PRIORITY_TICKERS)
    if universe == "hose":
        hose = hose_tickers()
        if hose:
            tickers = hose
    for t in PRIORITY_TICKERS:          # luôn đảm bảo có đủ nhóm ưu tiên
        if t not in tickers:
            tickers.append(t)
    print(f"Chế độ: rebuild={rebuild} | universe={universe}")
    print(f"Giờ VN: {now:%Y-%m-%d %H:%M} | {len(tickers)} mã | kỳ vọng phiên {expected_latest_date(now)}")

    if rebuild:   # coi như chưa có dữ liệu -> tải lại đủ lịch sử; dòng cũ vẫn giữ làm dự phòng nếu mã nào lỗi
        counts, lasts = {}, {}
    else:
        counts = existing.groupby("ticker").size().to_dict()
        lasts = existing.groupby("ticker")["date"].max().to_dict()

    new_parts, failed = [], []
    for i, sym in enumerate(tickers, 1):
        if counts.get(sym, 0) < MIN_ROWS:
            start = (now - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
        else:
            start = (datetime.strptime(lasts[sym], "%Y-%m-%d") - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
        df = fetch_best(sym, start, today)
        if df.empty:
            failed.append(sym)
            print(f"[{i}/{len(tickers)}] {sym}: KHÔNG có dữ liệu")
        else:
            new_parts.append(to_rows(sym, df))
            print(f"[{i}/{len(tickers)}] {sym}: +{len(df)} dòng, tới {df['time'].max():%Y-%m-%d}")
        time.sleep(SLEEP_BETWEEN)

    if new_parts:
        fresh = pd.concat(new_parts, ignore_index=True)
        merged = pd.concat([existing, fresh], ignore_index=True)
        merged = (merged.drop_duplicates(subset=["ticker", "date"], keep="last")
                        .sort_values(["ticker", "date"]).reset_index(drop=True))
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        merged.to_csv(CSV_PATH, index=False)
        print(f"Đã ghi {CSV_PATH}: {len(merged)} dòng.")
        upsert_supabase(fresh)
    else:
        merged = existing
        print("Không lấy được dòng mới nào.")

    # ---- Kiểm tra độ mới: báo ĐỎ nếu vẫn cũ ----
    expected = expected_latest_date(now)
    latest = pd.to_datetime(merged["date"]).max().date() if len(merged) else None
    ok = latest is not None and latest >= expected
    print(f"Ngày mới nhất trong CSV: {latest} | kỳ vọng: {expected} | lỗi: {len(failed)}/{len(tickers)} mã")
    if failed:
        print("Mã lỗi:", ", ".join(failed))
    if not ok:
        print("!! DỮ LIỆU VẪN CŨ (có thể là ngày lễ hoặc nguồn chưa cập nhật).")
        sys.exit(1)
    if len(failed) > len(tickers) * 0.3:
        print("!! Quá nhiều mã lỗi.")
        sys.exit(1)


if __name__ == "__main__":
    main()
