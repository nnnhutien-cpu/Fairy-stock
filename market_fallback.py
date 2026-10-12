"""
market_fallback.py - Nguồn dự phòng cho Tab 1 (Thị Trường).

Dùng khi market_snapshot() trả về rỗng. Không phụ thuộc streamlit nên test được độc lập.
Cung cấp:
  - normalize_ohlcv(df)         : chuẩn hóa DataFrame giá về cột time/open/high/low/close/volume
  - fetch_tcbs_vnindex(days)    : lấy giá ngày VNINDEX trực tiếp từ API công khai TCBS (v1)
  - compute_snapshot(df)        : tính MA/RSI/MACD/Volume/Hỗ trợ-Kháng cự (cùng key với market_snapshot)
  - fallback_reco(snap, pe)     : khuyến nghị đơn giản khi trend_engine không trả được kết quả
"""
import time

import numpy as np
import pandas as pd

TCBS_BARS_URL = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"


def _num(x, default=None):
    try:
        if x is None or pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def normalize_ohlcv(df):
    """Trả về DataFrame [time, open, high, low, close, volume] sắp xếp tăng dần, hoặc None."""
    if df is None or len(df) == 0:
        return None
    d = df.copy()
    if isinstance(d.index, pd.DatetimeIndex):
        d = d.reset_index()
    d.columns = [str(c).lower().strip() for c in d.columns]

    if "time" not in d.columns:
        for cand in ("tradingdate", "date", "datetime", "index", "timestamp"):
            if cand in d.columns:
                d = d.rename(columns={cand: "time"})
                break
    d = d.loc[:, ~d.columns.duplicated()]
    if "time" not in d.columns or "close" not in d.columns:
        return None

    t = pd.to_datetime(d["time"], errors="coerce")
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    d["time"] = t

    for c in ("open", "high", "low", "close", "volume"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    if "high" not in d.columns:
        d["high"] = d["close"]
    if "low" not in d.columns:
        d["low"] = d["close"]
    if "open" not in d.columns:
        d["open"] = d["close"]
    if "volume" not in d.columns:
        d["volume"] = 0.0
    d["volume"] = d["volume"].fillna(0.0)

    d = d.dropna(subset=["time", "close"])
    d = d.sort_values("time").drop_duplicates("time", keep="last")
    if d.empty:
        return None
    return d[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def fetch_tcbs_vnindex(days=300, timeout=10):
    """Giá ngày VNINDEX từ API công khai TCBS. Ném lỗi nếu không lấy được."""
    import requests

    params = {
        "ticker": "VNINDEX",
        "type": "index",
        "resolution": "D",
        "to": int(time.time()),
        "countBack": int(days),
    }
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    r = requests.get(TCBS_BARS_URL, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    rows = (r.json() or {}).get("data") or []
    if not rows:
        raise ValueError("TCBS không trả về dữ liệu")
    out = normalize_ohlcv(pd.DataFrame(rows))
    if out is None:
        raise ValueError("TCBS trả về dữ liệu thiếu cột giá")
    return out


def compute_snapshot(df):
    """Tính snapshot thị trường từ giá ngày. Cùng tên key với market_snapshot() mà main.py đọc."""
    d = normalize_ohlcv(df)
    if d is None or len(d) < 30:
        raise ValueError("Không đủ dữ liệu giá (cần >= 30 phiên)")

    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    price = float(c.iloc[-1])
    prev = float(c.iloc[-2])

    ma20 = _num(c.rolling(20).mean().iloc[-1])
    ma50 = _num(c.rolling(50).mean().iloc[-1])
    ma200 = _num(c.rolling(200).mean().iloc[-1])

    # RSI(14) kiểu Wilder
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    g, ls = _num(gain.iloc[-1]), _num(loss.iloc[-1])
    if g is None or ls is None:
        rsi = None
    elif ls == 0:
        rsi = 100.0
    else:
        rsi = 100 - 100 / (1 + g / ls)

    # MACD 12/26/9
    macd_line = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    macd, signal = _num(macd_line.iloc[-1]), _num(macd_sig.iloc[-1])

    support = _num(l.tail(20).min(), 0.0)
    resist = _num(h.tail(20).max(), 0.0)

    vol_today = _num(v.iloc[-1], 0.0)
    vol_avg = _num(v.iloc[-21:-1].mean(), 0.0)
    vol_ratio = (vol_today / vol_avg) if vol_avg else 0.0

    # --- Nhãn tiếng Việt ---
    if ma20 is None:
        trend_text = "—"
    elif ma50 is not None and price > ma20 > ma50:
        trend_text = "Xu hướng TĂNG (giá > MA20 > MA50)"
    elif ma50 is not None and price < ma20 < ma50:
        trend_text = "Xu hướng GIẢM (giá < MA20 < MA50)"
    elif price >= ma20:
        trend_text = "Hồi phục / đi ngang phía trên MA20"
    else:
        trend_text = "Yếu / đi ngang phía dưới MA20"

    ma20_text = ""
    if ma20:
        ma20_text = f"Giá {'trên' if price >= ma20 else 'dưới'} MA20 {abs(price / ma20 - 1) * 100:.1f}%"

    if rsi is None:
        rsi_text = "—"
    elif rsi >= 70:
        rsi_text = "Quá mua"
    elif rsi <= 30:
        rsi_text = "Quá bán"
    elif rsi >= 50:
        rsi_text = "Động lượng tích cực"
    else:
        rsi_text = "Động lượng yếu"

    if vol_ratio >= 1.3:
        vol_text = "Thanh khoản cao hơn trung bình"
    elif vol_ratio and vol_ratio <= 0.7:
        vol_text = "Thanh khoản thấp hơn trung bình"
    elif vol_ratio:
        vol_text = "Thanh khoản quanh trung bình"
    else:
        vol_text = "—"

    return {
        "price": price,
        "change_pct": (price / prev - 1) * 100 if prev else 0.0,
        "date": d["time"].iloc[-1],
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "rsi": rsi, "rsi_text": rsi_text,
        "macd": macd, "macd_signal": signal,
        "macd_cross": ("Vàng" if (macd is not None and signal is not None and macd > signal) else "Chết")
        if (macd is not None and signal is not None) else "—",
        "support": support, "resistance": resist,
        "vol_today": vol_today, "vol_avg": vol_avg, "vol_ratio": vol_ratio,
        "trend_text": trend_text, "ma20_text": ma20_text, "vol_text": vol_text,
        "_source": "fallback",
    }


def fallback_reco(snap, pe_stats=None):
    """Khuyến nghị đơn giản: điểm từ vị trí giá so với MA, RSI, MACD, percentile P/E."""
    price = _num((snap or {}).get("price"))
    if price is None:
        return None

    score = 0
    for key, weight in (("ma20", 1), ("ma50", 1), ("ma200", 2)):
        m = _num(snap.get(key))
        if m is not None:
            score += weight if price >= m else -weight

    rsi = _num(snap.get("rsi"))
    if rsi is not None:
        if rsi >= 70:
            score -= 1
        elif rsi <= 30:
            score += 1

    macd, sig = _num(snap.get("macd")), _num(snap.get("macd_signal"))
    if macd is not None and sig is not None:
        score += 1 if macd > sig else -1

    pct = _num((pe_stats or {}).get("percentile"))
    if pct is not None:
        if pct < 25:
            score += 1
        elif pct > 75:
            score -= 1

    if score >= 4:
        action, color, stock = "TĂNG TỶ TRỌNG CỔ PHIẾU", "success", 80
    elif score >= 1:
        action, color, stock = "GIỮ – MUA THĂM DÒ", "info", 60
    elif score >= -2:
        action, color, stock = "THẬN TRỌNG – HẠN CHẾ MUA MỚI", "warning", 40
    else:
        action, color, stock = "GIẢM TỶ TRỌNG – BẢO TOÀN VỐN", "danger", 20

    return {"action": action, "color": color, "score": score,
            "stock": stock, "cash": 100 - stock, "source": "fallback"}
