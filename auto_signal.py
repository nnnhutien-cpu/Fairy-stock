"""
auto_signal.py
==============
Chạy bởi GitHub Actions mỗi 15 phút trong giờ giao dịch.
Pipeline:
  1. DNSE OpenAPI  → positions (mã đang giữ thực tế)
  2. vnstock       → giá + OHLCV lịch sử 300 phiên
  3. Tính Cô Tiên  → Kijun17 / Knife65 / Knife129
  4. Gán State + Advice tự động
  5. Ghi data/signals.json + data/log.json → git push

Secrets cần set trong GitHub repo:
  DNSE_API_KEY, DNSE_API_SECRET, DNSE_ACCOUNT_ID
  GH_TOKEN  (để push lên repo)
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

# ── vnstock ──────────────────────────────────────────────────────────
try:
    from vnstock import Vnstock
    VNSTOCK_OK = True
except ImportError:
    VNSTOCK_OK = False

# ── DNSE Python SDK ───────────────────────────────────────────────────
try:
    from dnse import DNSEClient
    DNSE_SDK_OK = True
except ImportError:
    DNSE_SDK_OK = False

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

DNSE_API_KEY    = os.environ.get("DNSE_API_KEY", "")
DNSE_API_SECRET = os.environ.get("DNSE_API_SECRET", "")
DNSE_ACCOUNT_ID = os.environ.get("DNSE_ACCOUNT_ID", "")
DNSE_BASE_URL   = "https://openapi.dnse.com.vn"

# Danh sách mã mặc định nếu không lấy được từ DNSE positions
DEFAULT_WATCHLIST = [
    "BSR", "DCM", "FPT", "HPG", "MBS", "MWG", "PVT",
    "SHB", "SHS", "SSI", "TPB", "VCB", "VHM", "VIB",
    "VIC", "VIX", "VND",
]

OUTPUT_SIGNALS = "data/signals.json"
OUTPUT_LOG     = "data/log.json"

VN_TZ = timezone.utc  # GitHub runner dùng UTC, Streamlit tự convert

# ═══════════════════════════════════════════════════════════════════════
# 1. LẤY DANH SÁCH MÃ TỪ DNSE POSITIONS
# ═══════════════════════════════════════════════════════════════════════

def get_dnse_positions() -> list[str]:
    """Lấy danh sách mã đang giữ thực tế từ DNSE account."""
    if not DNSE_SDK_OK or not DNSE_API_KEY:
        print("[DNSE] SDK không có hoặc thiếu credentials → dùng watchlist mặc định")
        return []
    try:
        client = DNSEClient(
            api_key=DNSE_API_KEY,
            api_secret=DNSE_API_SECRET,
            base_url=DNSE_BASE_URL,
        )
        status, body = client.get_positions(account_id=DNSE_ACCOUNT_ID, dry_run=False)
        if status != 200 or not body:
            print(f"[DNSE] get_positions HTTP {status}")
            return []
        # body là list dict, mỗi item có 'symbol'
        tickers = []
        items = body if isinstance(body, list) else body.get("data", [])
        for item in items:
            sym = item.get("symbol") or item.get("instrumentCode") or ""
            if sym:
                tickers.append(sym.upper().strip())
        print(f"[DNSE] Positions: {tickers}")
        return tickers
    except Exception as e:
        print(f"[DNSE] Lỗi: {e}")
        return []


def get_dnse_balance() -> dict:
    """Lấy số dư tài khoản từ DNSE."""
    if not DNSE_SDK_OK or not DNSE_API_KEY:
        return {}
    try:
        client = DNSEClient(
            api_key=DNSE_API_KEY,
            api_secret=DNSE_API_SECRET,
            base_url=DNSE_BASE_URL,
        )
        status, body = client.get_balances(account_id=DNSE_ACCOUNT_ID, dry_run=False)
        if status == 200 and body:
            return body if isinstance(body, dict) else {}
    except Exception as e:
        print(f"[DNSE] balance lỗi: {e}")
    return {}


# ═══════════════════════════════════════════════════════════════════════
# 2. LẤY DỮ LIỆU GIÁ TỪ VNSTOCK
# ═══════════════════════════════════════════════════════════════════════

def fetch_price_data(ticker: str, days: int = 300) -> pd.DataFrame | None:
    """Lấy OHLCV từ vnstock, fallback Yahoo Finance."""
    # --- vnstock ---
    if VNSTOCK_OK:
        try:
            stock = Vnstock().stock(symbol=ticker, source="VCI")
            end   = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
            df = stock.quote.history(start=start, end=end, interval="1D")
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                for col in ("close", "open", "high", "low", "volume"):
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["close"])
                if len(df) >= 30:
                    return df
        except Exception as e:
            print(f"[vnstock] {ticker}: {e}")

    # --- Yahoo Finance fallback ---
    try:
        import yfinance as yf
        yf_ticker = ticker + ".VN"
        df = yf.download(yf_ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            df = df.dropna(subset=["close"])
            if len(df) >= 30:
                return df
    except Exception as e:
        print(f"[Yahoo] {ticker}: {e}")

    return None


# ═══════════════════════════════════════════════════════════════════════
# 3. TÍNH CÔ TIÊN INDICATORS
# ═══════════════════════════════════════════════════════════════════════

def kijun(close: pd.Series, high: pd.Series, low: pd.Series, period: int) -> float:
    """Kijun = (max_high + min_low) / 2 trong `period` phiên."""
    if len(close) < period:
        return float("nan")
    h = high.iloc[-period:].max()
    l = low.iloc[-period:].min()
    return (h + l) / 2


def knife(close: pd.Series, period: int) -> float:
    """Knife = EMA của close trong `period` phiên."""
    if len(close) < period:
        return float("nan")
    return close.ewm(span=period, adjust=False).mean().iloc[-1]


def rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/period, min_periods=period).mean()
    al = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    val = (100 - (100 / (1 + rs))).fillna(50)
    return round(val.iloc[-1], 1)


def compute_signals(ticker: str, df: pd.DataFrame) -> dict:
    """
    Tính State + Advice dựa hệ Cô Tiên.

    State:
      - Vùng Mua  : giá > Kijun17 VÀ giá > Knife65 VÀ giá > Knife129
      - Vùng Giữ  : giá > Kijun17 VÀ (giá < Knife65 HOẶC giá < Knife129)
      - Vùng Bán  : giá < Kijun17 VÀ giá > Knife65
      - Vùng Né   : giá < Kijun17 VÀ giá < Knife65 VÀ giá < Knife129

    Advice:
      Vùng Mua  → MUA
      Vùng Giữ  → GIỮ CP
      Vùng Bán  → BÁN 25%
      Vùng Né   → BÁN HẾT
    """
    close  = df["close"]
    high   = df["high"]   if "high"   in df.columns else close
    low    = df["low"]    if "low"    in df.columns else close
    volume = df["volume"] if "volume" in df.columns else pd.Series([0]*len(close))

    price  = round(close.iloc[-1], 2)
    prev   = round(close.iloc[-2], 2) if len(close) > 1 else price
    change = round((price - prev) / prev * 100, 2) if prev > 0 else 0.0

    k17    = kijun(close, high, low, 17)
    kf65   = knife(close, 65)
    kf129  = knife(close, 129)
    rsi14  = rsi(close, 14)

    vol_last = volume.iloc[-1]
    vol_ma20 = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else vol_last
    vol_ratio = round(vol_last / vol_ma20, 2) if vol_ma20 > 0 else 1.0

    # ── State logic ──
    above_k17  = price > k17   if not np.isnan(k17)   else False
    above_kf65 = price > kf65  if not np.isnan(kf65)  else False
    above_kf129= price > kf129 if not np.isnan(kf129) else False

    if above_k17 and above_kf65 and above_kf129:
        state = "Vùng Mua"
    elif above_k17 and (not above_kf65 or not above_kf129):
        state = "Vùng Giữ"
    elif not above_k17 and above_kf65:
        state = "Vùng Bán"
    else:
        state = "Vùng Né"

    # ── Advice logic ──
    advice_map = {
        "Vùng Mua":  "MUA",
        "Vùng Giữ":  "GIỮ CP",
        "Vùng Bán":  "BÁN 25%",
        "Vùng Né":   "BÁN HẾT",
    }
    advice = advice_map[state]

    # ── RSI override ──
    if rsi14 >= 75 and advice == "GIỮ CP":
        advice = "BÁN 25%"  # RSI quá mua → bán bớt
    if rsi14 <= 25 and advice == "BÁN 25%":
        advice = "GIỮ CP"   # RSI quá bán → chờ thêm

    return {
        "ticker":    ticker,
        "price":     price,
        "change":    change,
        "state":     state,
        "advice":    advice,
        "kijun17":   round(k17,   2) if not np.isnan(k17)   else None,
        "knife65":   round(kf65,  2) if not np.isnan(kf65)  else None,
        "knife129":  round(kf129, 2) if not np.isnan(kf129) else None,
        "rsi14":     rsi14,
        "vol_ratio": vol_ratio,
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


# ═══════════════════════════════════════════════════════════════════════
# 4. LẤY VNINDEX STATE
# ═══════════════════════════════════════════════════════════════════════

def get_vnindex_state() -> dict:
    """Lấy giá + trạng thái VN-Index."""
    result = {"price": 0, "change": 0.0, "state": "Sideways"}
    try:
        if VNSTOCK_OK:
            stock = Vnstock().stock(symbol="VNINDEX", source="VCI")
            end   = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
            df = stock.quote.history(start=start, end=end, interval="1D")
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                close = pd.to_numeric(df["close"], errors="coerce").dropna()
                price = round(close.iloc[-1], 2)
                prev  = round(close.iloc[-2], 2) if len(close) > 1 else price
                change = round((price - prev) / prev * 100, 2)
                ma20  = close.rolling(20).mean().iloc[-1]
                ma50  = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else ma20
                if price > ma20 and price > ma50:
                    state = "Uptrend"
                elif price < ma20 and price < ma50:
                    state = "Downtrend"
                else:
                    state = "Sideways"
                result = {"price": price, "change": change, "state": state}
    except Exception as e:
        print(f"[VNINDEX] {e}")
    return result


# ═══════════════════════════════════════════════════════════════════════
# 5. LOG
# ═══════════════════════════════════════════════════════════════════════

def append_log(message: str, log_path: str = OUTPUT_LOG):
    """Thêm 1 dòng log vào log.json (giữ 200 dòng gần nhất)."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logs = []
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.append({
        "time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "msg":  message,
    })
    logs = logs[-200:]  # giữ 200 dòng
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# 6. MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{now_str}] Bắt đầu auto_signal.py")

    os.makedirs("data", exist_ok=True)

    # ── Bước 1: lấy danh sách mã ──
    dnse_tickers = get_dnse_positions()
    watchlist = dnse_tickers if dnse_tickers else DEFAULT_WATCHLIST
    # Luôn giữ VNINDEX để tính market state
    append_log(f"Bắt đầu quét {len(watchlist)} mã: {', '.join(watchlist)}")

    # ── Bước 2: lấy VNINDEX state ──
    vnindex = get_vnindex_state()
    append_log(f"VNINDEX {vnindex['price']} ({vnindex['change']:+.2f}%) → {vnindex['state']}")

    # ── Bước 3: tính signal từng mã ──
    signals = []
    errors  = []
    for ticker in watchlist:
        try:
            df = fetch_price_data(ticker, days=300)
            if df is None or df.empty:
                errors.append(ticker)
                append_log(f"⚠ {ticker}: không lấy được dữ liệu giá")
                continue
            sig = compute_signals(ticker, df)
            signals.append(sig)
            append_log(f"✓ {ticker}: {sig['price']} | {sig['state']} | Advice: {sig['advice']}")
            print(f"  {ticker}: {sig['state']} → {sig['advice']}")
        except Exception as e:
            errors.append(ticker)
            append_log(f"✗ {ticker}: {e}")
            print(f"  {ticker} LỖI: {e}")

    # ── Bước 4: lấy balance DNSE ──
    balance = get_dnse_balance()

    # ── Bước 5: ghi signals.json ──
    output = {
        "updated_at": now_str,
        "vnindex":    vnindex,
        "balance":    balance,
        "signals":    signals,
        "errors":     errors,
        "watchlist":  watchlist,
    }
    with open(OUTPUT_SIGNALS, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    append_log(f"✅ Hoàn tất: {len(signals)}/{len(watchlist)} mã | VNINDEX {vnindex['state']}")
    print(f"[DONE] {len(signals)} signals → {OUTPUT_SIGNALS}")


if __name__ == "__main__":
    main()
