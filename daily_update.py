"""
daily_update.py — Phiên bản DNSE API (bỏ Supabase)
====================================================
Lấy OHLCV ~7 ngày gần nhất từ DNSE Chart API (public, không cần auth)
cho toàn bộ mã niêm yết, lưu vào data/stock_prices.csv.

GitHub Actions commit file CSV lên repo sau mỗi lần chạy.
Streamlit đọc CSV từ repo → không cần Supabase, không cần DB.

Cách chạy local:
    python daily_update.py

Cách chạy GitHub Actions: xem .github/workflows/daily_update.yml
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# ── Cấu hình ──────────────────────────────────────────────────────────────────
DAYS_BACK   = 7        # đủ bù nghỉ lễ dài
DATA_DIR    = Path("data")
OUTPUT_CSV  = DATA_DIR / "stock_prices.csv"
DNSE_BASE   = "https://services.entrade.com.vn/chart/history"
RATE_SLEEP  = 0.3      # giây giữa các request (DNSE không giới hạn ngặt như vnstock)

# ── Danh sách mã dự phòng nếu không lấy được từ API ──────────────────────────
FALLBACK_TICKERS = [
    "HPG","SSI","VND","FPT","TCB","MBB","MWG","VIC","VHM","VNM",
    "ACB","BID","CTG","VCB","HDB","MSN","GAS","PLX","PVD","DGC",
]


def get_all_tickers() -> list[str]:
    """Lấy danh sách mã từ DNSE instruments API."""
    try:
        url = "https://openapi.dnse.com.vn/market-data/instruments"
        resp = requests.get(url, timeout=15)
        if resp.ok:
            data = resp.json()
            # DNSE trả về list các instrument, lọc loại cổ phiếu (ST)
            tickers = [
                item["symbol"] for item in data
                if isinstance(item, dict)
                and item.get("productGrpId") in ("ST", "STOCK", None)
                and item.get("symbol")
                and len(item["symbol"]) <= 5   # loại bỏ mã phái sinh dài
                and not item["symbol"].startswith("VN30F")
            ]
            if tickers:
                print(f"✅ DNSE instruments: {len(tickers)} mã")
                return sorted(set(tickers))
    except Exception as e:
        print(f"⚠️  DNSE instruments API lỗi: {e}")

    # Fallback: dùng vnstock nếu cài
    try:
        from vnstock.api.listing import Listing
        for src in ["vci", "kbs"]:
            try:
                df = Listing(source=src).symbols_by_exchange()
                df.columns = [str(c).lower().strip() for c in df.columns]
                type_col = next((c for c in df.columns if "type" in c), None)
                if type_col:
                    df = df[df[type_col].astype(str).str.upper().isin(["STOCK", "CP"])]
                if "exchange" in df.columns:
                    df = df[df["exchange"].astype(str).str.upper().isin(["HOSE","HSX","HNX","UPCOM"])]
                col = next((c for c in ["symbol","ticker"] if c in df.columns), None)
                if col:
                    lst = sorted({str(t).strip().upper() for t in df[col].dropna() if str(t).strip()})
                    if lst:
                        print(f"✅ vnstock ({src}): {len(lst)} mã")
                        return lst
            except Exception:
                continue
    except ImportError:
        pass

    print(f"⚠️  Dùng danh sách dự phòng {len(FALLBACK_TICKERS)} mã")
    return FALLBACK_TICKERS


def fetch_ohlcv_dnse(symbol: str, start_ts: int, end_ts: int) -> pd.DataFrame:
    """
    Lấy OHLCV từ DNSE Chart API (public endpoint, không cần API key).
    Trả về DataFrame rỗng nếu lỗi.
    """
    try:
        resp = requests.get(
            DNSE_BASE,
            params={
                "symbol":     symbol.upper(),
                "resolution": "D",
                "from":       start_ts,
                "to":         end_ts,
            },
            timeout=10,
        )
        if not resp.ok:
            return pd.DataFrame()

        data = resp.json()
        if data.get("s") != "ok" or not data.get("t"):
            return pd.DataFrame()

        df = pd.DataFrame({
            "ticker": symbol.upper(),
            "date":   pd.to_datetime(data["t"], unit="s").strftime("%Y-%m-%d"),
            "open":   [float(x) for x in data["o"]],
            "high":   [float(x) for x in data["h"]],
            "low":    [float(x) for x in data["l"]],
            "close":  [float(x) for x in data["c"]],
            "volume": [int(x)   for x in data["v"]],
        })
        return df

    except Exception:
        return pd.DataFrame()


def load_existing() -> pd.DataFrame:
    """Đọc CSV hiện tại nếu có."""
    if OUTPUT_CSV.exists():
        try:
            df = pd.read_csv(OUTPUT_CSV, dtype={"date": str})
            print(f"📂 Đọc cache: {len(df):,} dòng từ {OUTPUT_CSV}")
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["ticker","date","open","high","low","close","volume"])


def save_csv(df: pd.DataFrame):
    """Lưu CSV, sort theo ticker + date."""
    DATA_DIR.mkdir(exist_ok=True)
    df = df.drop_duplicates(subset=["ticker","date"]).sort_values(
        ["ticker","date"]
    ).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"💾 Đã lưu {len(df):,} dòng → {OUTPUT_CSV}")


def main():
    tickers = get_all_tickers()
    print(f"\n🚀 Cập nhật {len(tickers)} mã — {DAYS_BACK} ngày gần nhất\n")

    end_ts   = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=DAYS_BACK + 3)).timestamp())

    existing = load_existing()
    new_rows = []
    ok, fail, skip = 0, 0, 0

    t0 = time.time()
    for idx, ticker in enumerate(tickers, 1):
        df = fetch_ohlcv_dnse(ticker, start_ts, end_ts)
        time.sleep(RATE_SLEEP)

        if df.empty:
            fail += 1
        else:
            new_rows.append(df)
            ok += 1

        if idx % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / idx * (len(tickers) - idx)
            print(f"  [{idx:4d}/{len(tickers)}] ✅{ok} ❌{fail} — {elapsed:.0f}s qua, ~{eta:.0f}s còn")

    if not new_rows:
        print("❌ Không lấy được dữ liệu nào từ DNSE!")
        sys.exit(1)

    # Merge với data cũ (upsert theo ticker+date)
    new_df = pd.concat(new_rows, ignore_index=True)
    if not existing.empty:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    save_csv(combined)

    elapsed = time.time() - t0
    print(f"\n🎉 Xong: ✅{ok} mã cập nhật | ❌{fail} mã lỗi | ⏱️{elapsed:.0f}s")
    print(f"   File: {OUTPUT_CSV} ({OUTPUT_CSV.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
