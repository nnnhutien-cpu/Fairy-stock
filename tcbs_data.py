"""
tcbs_data.py - lấy giá trực tiếp từ API public của TCBS (thay cho vnstock)

Cung cấp:
  fetch_bars(symbol, start, end, resolution)        -> 1 lần gọi API
  fetch_bars_range(symbol, start, end, resolution)  -> tự chia nhỏ khoảng ngày dài
  scale_to_thousand(df, symbol)                     -> đưa giá cổ phiếu về đơn vị nghìn đồng
  Vnstock().stock(...).quote.history(...)           -> lớp tương thích cú pháp cũ

Trả về DataFrame: time, open, high, low, close, volume (giống vnstock).

LƯU Ý: đây là API không chính thức, chưa được kiểm chứng từ phía tác giả file.
Nếu lỗi/rỗng: mở trang TCBS -> F12 -> Network để lấy URL & tham số hiện hành.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

TCBS_BARS_URL = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"

VN_TZ = timezone(timedelta(hours=7))
INDEX_SYMBOLS = {"VNINDEX", "VN30", "HNXINDEX", "HNX30", "UPCOMINDEX", "VNALL"}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://tcinvest.tcbs.com.vn",
    "Referer": "https://tcinvest.tcbs.com.vn/",
}

# Chú ý phân biệt: "1M" = tháng, "1m" = 1 phút
_RES_MAP = {
    "1D": "D", "D": "D", "1W": "W", "W": "W", "1M": "M", "M": "M",
    "1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "60m": "60",
    "1": "1", "5": "5", "15": "15", "30": "30", "60": "60",
}
_OHLC = ("open", "high", "low", "close")


def _ts(date_str: str, end_of_day: bool = False) -> int:
    dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").replace(tzinfo=VN_TZ)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())


def scale_to_thousand(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Đưa giá cổ phiếu về đơn vị NGHÌN ĐỒNG (vd 65.5) như vnstock/Supabase.
    - Chỉ số (VNINDEX...) giữ nguyên.
    - Cổ phiếu: nếu giá trung vị >= 500 thì API đang trả đồng -> chia 1000.
      (Không có cổ phiếu VN nào giá >= 500 nghìn đồng, nên ngưỡng này an toàn.)
    """
    if df is None or df.empty or symbol.upper() in INDEX_SYMBOLS:
        return df
    med = pd.to_numeric(df.get("close"), errors="coerce").median()
    if pd.notna(med) and med >= 500:
        df = df.copy()
        for c in _OHLC:
            if c in df.columns:
                df[c] = df[c] / 1000.0
    return df


def fetch_bars(symbol: str, start: str, end: str = None,
               resolution: str = "D", timeout: float = 12) -> pd.DataFrame:
    """Gọi 1 lần API bars của TCBS. start/end dạng 'YYYY-MM-DD' (giờ VN)."""
    symbol = symbol.upper()
    end = end or datetime.now(VN_TZ).strftime("%Y-%m-%d")
    res = _RES_MAP.get(resolution, resolution)
    params = {
        "ticker": symbol,
        "type": "index" if symbol in INDEX_SYMBOLS else "stock",
        "resolution": res,
        "from": _ts(start),
        "to": _ts(end, end_of_day=True),
    }
    r = requests.get(TCBS_BARS_URL, params=params, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    rows = (r.json() or {}).get("data") or []
    if not rows:
        return pd.DataFrame()

    raw = pd.DataFrame(rows)
    if "tradingDate" not in raw.columns:
        return pd.DataFrame()

    t = (pd.to_datetime(raw["tradingDate"], utc=True, errors="coerce")
           .dt.tz_convert(VN_TZ).dt.tz_localize(None))
    if res in ("D", "W", "M"):
        t = t.dt.normalize()

    def col(name):
        return pd.to_numeric(raw[name], errors="coerce") if name in raw.columns else np.nan

    out = pd.DataFrame({"time": t})
    for c in _OHLC:
        out[c] = col(c)
    out["volume"] = col("volume")

    out = (out.dropna(subset=["time", "close"])
              .drop_duplicates(subset=["time"])
              .sort_values("time")
              .reset_index(drop=True))
    return scale_to_thousand(out, symbol)


def fetch_bars_range(symbol: str, start: str, end: str = None,
                     resolution: str = "D", chunk_days: int = 700,
                     timeout: float = 12) -> pd.DataFrame:
    """Chia khoảng ngày dài thành nhiều đoạn (tránh giới hạn số nến mỗi lần gọi)."""
    end = end or datetime.now(VN_TZ).strftime("%Y-%m-%d")
    d0 = datetime.strptime(str(start)[:10], "%Y-%m-%d")
    d1 = datetime.strptime(str(end)[:10], "%Y-%m-%d")
    frames, cur = [], d0
    while cur <= d1:
        nxt = min(cur + timedelta(days=chunk_days), d1)
        part = fetch_bars(symbol, cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"),
                          resolution, timeout)
        if not part.empty:
            frames.append(part)
        cur = nxt + timedelta(days=1)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)


# ----------------------------------------------------------
# Lớp tương thích: Vnstock().stock(symbol=..., source=...).quote.history(...)
# ----------------------------------------------------------
class _Quote:
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()

    def history(self, start: str, end: str = None, interval: str = "1D", **_):
        df = fetch_bars_range(self.symbol, start, end, interval)
        if df.empty:
            raise ValueError(f"TCBS không trả dữ liệu cho {self.symbol} ({start} -> {end})")
        return df


class _Stock:
    def __init__(self, symbol: str):
        self.quote = _Quote(symbol)


class Vnstock:
    def stock(self, symbol: str, source: str = "TCBS"):
        return _Stock(symbol)
