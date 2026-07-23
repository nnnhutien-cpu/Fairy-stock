import os
import json
import re as _re
import datetime as _dt
import numpy as _np
import pandas as _pd
import streamlit as _st

# ============================================================
#  CONSTANTS
# ============================================================
_MKT_CACHE_DIR = "data/valuation"
_MKT_HIST_FILE = os.path.join(_MKT_CACHE_DIR, "vnindex_pe_history.csv")
_MKT_META_FILE = os.path.join(_MKT_CACHE_DIR, "vnindex_pe_meta.json")
os.makedirs(_MKT_CACHE_DIR, exist_ok=True)

PE_HIST_TTL = 86400  # 1 ngày

# ============================================================
#  P/E VN-INDEX THEO NĂM (hard-coded)
#  Nguồn: FiinTrade, HoSE, Bloomberg — P/E cuối năm (trailing)
# ============================================================
_PE_YEARLY = {
    2005: 15.5, 2006: 25.2, 2007: 34.5, 2008: 10.8,
    2009: 14.1, 2010: 13.2, 2011:  9.8, 2012: 11.2,
    2013: 13.5, 2014: 12.8, 2015: 12.5, 2016: 13.9,
    2017: 18.2, 2018: 15.8, 2019: 16.5, 2020: 16.8,
    2021: 18.3, 2022: 10.3, 2023: 13.1, 2024: 13.9,
    2025: 13.4,  # ước tính
}

# EPS VN-INDEX theo ĐIỂM (= Giá EOY / P/E EOY)
# Dùng để nội suy P/E hiện tại từ giá VNINDEX real-time (fallback)
_EPS_POINTS = {
    year: round(price / pe, 4)
    for year, (price, pe) in {
        2005: ( 307.5, 15.5), 2006: ( 751.8, 25.2), 2007: ( 927.0, 34.5),
        2008: ( 315.6, 10.8), 2009: ( 494.8, 14.1), 2010: ( 484.7, 13.2),
        2011: ( 351.6,  9.8), 2012: ( 413.7, 11.2), 2013: ( 504.6, 13.5),
        2014: ( 545.6, 12.8), 2015: ( 579.0, 12.5), 2016: ( 664.9, 13.9),
        2017: ( 984.2, 18.2), 2018: ( 892.5, 15.8), 2019: (1007.1, 16.5),
        2020: (1103.9, 16.8), 2021: (1498.3, 18.3), 2022: ( 998.7, 10.3),
        2023: (1129.9, 13.1), 2024: (1266.8, 13.9),
        # 2025 chưa chốt EOY → không hard-code, dùng EPS 2024 làm trailing
    }.items()
}


# ============================================================
#  STOCK-LEVEL VALUATION
# ============================================================
def get_stock_valuation(ticker, ichi_status, price_val):
    pe, pb, von_hoa = 0.0, 0.0, 0.0
    try:
        try:
            from vnstock.stock import ticker_overview
        except ImportError:
            from vnstock import ticker_overview
        df_overview = ticker_overview(ticker)
        if df_overview is not None and not df_overview.empty:
            df_overview.columns = [str(c).lower().strip() for c in df_overview.columns]
            if 'outstandingshare' in df_overview.columns:
                p_vnd = price_val * 1000 if price_val < 500 else price_val
                out_share = float(df_overview['outstandingshare'].iloc[0])
                von_hoa = (out_share * p_vnd) / 1000
            if 'pe' in df_overview.columns: pe = df_overview['pe'].iloc[0]
            if 'pb' in df_overview.columns: pb = df_overview['pb'].iloc[0]
    except Exception:
        pass

    if pe == 0.0 and pb == 0.0:
        try:
            try:
                from vnstock.stock import financial_ratio
            except ImportError:
                from vnstock import financial_ratio
            df_ratio = financial_ratio(ticker, 'quarterly', True)
            if df_ratio is not None and not df_ratio.empty:
                df_ratio.columns = [str(c).lower().strip() for c in df_ratio.columns]
                if 'pe' in df_ratio.columns: pe = df_ratio['pe'].iloc[0]
                elif 'pricetoearning' in df_ratio.columns: pe = df_ratio['pricetoearning'].iloc[0]
                if 'pb' in df_ratio.columns: pb = df_ratio['pb'].iloc[0]
                elif 'pricetobook' in df_ratio.columns: pb = df_ratio['pricetobook'].iloc[0]
        except Exception:
            pass

    pe      = round(float(pe), 2)      if _pd.notna(pe)      else 0.0
    pb      = round(float(pb), 2)      if _pd.notna(pb)      else 0.0
    von_hoa = round(float(von_hoa), 2) if _pd.notna(von_hoa) else 0.0

    if pe == 0.0 and pb == 0.0:
        danh_gia = "⚠️ Đang tính toán"
    elif "Dưới Mây" in str(ichi_status):
        danh_gia = "📉 Định giá Thấp (Rẻ)"
    elif "Trên Mây" in str(ichi_status):
        danh_gia = "📈 Định giá Cao (Đắt)"
    else:
        danh_gia = "⚖️ Hợp lý (Trong mây)"

    return {"P/E": pe, "P/B": pb, "Vốn Hóa (Tỷ)": von_hoa, "Đánh Giá": danh_gia}


# ============================================================
#  MARKET-LEVEL P/E — scrape từ 24hmoney (SSR HTML)
# ============================================================

@_st.cache_data(ttl=3600, show_spinner=False)  # cache 1 tiếng
def scrape_vnindex_pe() -> "dict | None":
    """
    Scrape P/E và P/B VN-INDEX từ 24hmoney.vn/indices/vn-index.

    Trang dùng Nuxt SSR — P/E và P/B render sẵn trong HTML,
    không cần API key, không cần cookie/login.

    Xác nhận: trang trả "P/E 13.18" và "P/B 2.04" dạng text thô.

    Trả về: {"pe": float, "pb": float} hoặc None nếu lỗi.
    """
    import requests as _req

    URL = "https://24hmoney.vn/indices/vn-index"
    HDR = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": "https://24hmoney.vn/",
    }
    try:
        r = _req.get(URL, headers=HDR, timeout=10)
        if r.status_code != 200:
            return None
        html = r.text

        # HTML chứa dạng: "P/E 13.18" và "P/B 2.04" (text thô, SSR)
        # Regex: bắt số thập phân ngay sau "P/E" hoặc "P/B", có thể có
        # ký tự HTML ở giữa (tag, khoảng trắng)
        pe_match = _re.search(r'P/E[\s\S]{0,60}?(\d{1,3}\.\d{1,2})(?!\d)', html)
        pb_match = _re.search(r'P/B[\s\S]{0,60}?(\d{1,3}\.\d{1,2})(?!\d)', html)

        result = {}
        if pe_match:
            val = float(pe_match.group(1))
            if 1 < val < 100:   # sanity check
                result["pe"] = round(val, 2)
        if pb_match:
            val = float(pb_match.group(1))
            if 0.1 < val < 20:  # sanity check
                result["pb"] = round(val, 2)

        return result if result else None
    except Exception:
        return None


def get_current_pe(vnindex_price=None):
    """
    Lấy P/E VN-INDEX hiện tại theo thứ tự ưu tiên:

    1. scrape_vnindex_pe() — 24hmoney SSR HTML (nguồn thực tế, cache 1h)
    2. Fallback: tính từ EPS trailing năm trước (hard-coded)

    KHÔNG truyền string "VNINDEX" vào đây — vnindex_price phải là float.
    """
    # Ưu tiên 1: scrape 24hmoney
    live = scrape_vnindex_pe()
    if live and live.get("pe"):
        return live["pe"]

    # Fallback: tính xấp xỉ từ EPS trailing
    if vnindex_price is None:
        return None
    try:
        price = float(vnindex_price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    try:
        year = _dt.date.today().year
        # Dùng EPS năm trước (đã chốt), fallback năm kia
        eps = _EPS_POINTS.get(year - 1) or _EPS_POINTS.get(year - 2)
        if eps and eps > 0:
            return round(price / eps, 2)
    except Exception:
        pass
    return None


def get_current_pb() -> "float | None":
    """Lấy P/B VN-INDEX từ 24hmoney (cùng request với P/E, free từ cache)."""
    live = scrape_vnindex_pe()
    if live and live.get("pb"):
        return live["pb"]
    return None


@_st.cache_data(ttl=PE_HIST_TTL, show_spinner=False)
def get_pe_history(years: int = 20) -> "_pd.DataFrame":
    """P/E lịch sử từ bảng hard-coded — không cần API key."""
    if os.path.exists(_MKT_HIST_FILE):
        try:
            df = _pd.read_csv(_MKT_HIST_FILE, parse_dates=["date"])
            if len(df) > 0 and (_dt.date.today() - df["date"].max().date()).days < 60:
                return df
        except Exception:
            pass

    df = _build_pe_history(years)
    if df is not None and not df.empty:
        try:
            df.to_csv(_MKT_HIST_FILE, index=False)
            with open(_MKT_META_FILE, "w") as f:
                json.dump({"last_update": _dt.date.today().isoformat(), "n_points": len(df)}, f)
        except Exception:
            pass
    return df if df is not None else _pd.DataFrame(columns=["date", "pe"])


def _build_pe_history(years: int) -> "_pd.DataFrame":
    cutoff = _dt.date.today().year - years
    rows = []
    for year, pe in sorted(_PE_YEARLY.items()):
        if year < cutoff:
            continue
        rows.append({"date": _pd.Timestamp(f"{year}-12-31"), "pe": pe})
    if not rows:
        return None
    df = _pd.DataFrame(rows)
    df["pe"] = df["pe"].clip(lower=3, upper=50)
    return df


# ============================================================
#  THỐNG KÊ & NHẬN XÉT
# ============================================================
def pe_stats(pe_hist: "_pd.DataFrame", pe_now: "float | None") -> dict:
    if pe_hist is None or pe_hist.empty or pe_now is None:
        return {
            "pe_now": pe_now, "mean": None, "median": None,
            "stdev": None, "min": None, "max": None,
            "percentile": None, "zscore": None, "pct_vs_avg": None,
            "comment": "⏳ Đang tải dữ liệu lịch sử…",
        }
    series = pe_hist["pe"].astype(float)
    mean   = float(series.mean())
    median = float(series.median())
    stdev  = float(series.std())
    pmin   = float(series.min())
    pmax   = float(series.max())
    pct    = float((series < pe_now).sum() / len(series) * 100)
    z      = (pe_now - mean) / stdev if stdev > 0 else 0
    pct_vs = (pe_now - mean) / mean * 100 if mean > 0 else 0

    # Ngưỡng 88% thay vì 85% để P/E ~18x (bình thường cuối chu kỳ tăng,
    # ví dụ 2017: 18.2x, 2021: 18.3x) không bị xếp "Đắt kỷ lục" sai.
    # Bảng 21 năm có 2 outlier bong bóng (2006: 25x, 2007: 34x) kéo lệch phân phối.
    if pct < 20:
        comment = (f"💎 **RẺ kỷ lục** — P/E={pe_now:.1f}x percentile {pct:.0f}%, "
                   f"thấp hơn TB {abs(pct_vs):.0f}%. Cơ hội tích lũy dài hạn.")
    elif pct < 35:
        comment = (f"🟢 **Vùng rẻ** — P/E={pe_now:.1f}x percentile {pct:.0f}%. "
                   f"Thị trường đang định giá hấp dẫn so với lịch sử.")
    elif pct < 65:
        comment = (f"🟡 **Hợp lý** — P/E={pe_now:.1f}x percentile {pct:.0f}%. "
                   f"Định giá cân bằng, không có tín hiệu rõ ràng.")
    elif pct < 88:
        comment = (f"🟠 **Vùng đắt** — P/E={pe_now:.1f}x percentile {pct:.0f}%. "
                   f"Nên thận trọng, hạn chế mua đuổi.")
    else:
        comment = (f"🔴 **Đắt kỷ lục** — P/E={pe_now:.1f}x percentile {pct:.0f}%. "
                   f"Cảnh giác rủi ro điều chỉnh, ưu tiên chốt lời.")

    return {
        "pe_now":     round(pe_now, 2),
        "mean":       round(mean, 2),
        "median":     round(median, 2),
        "stdev":      round(stdev, 2),
        "min":        round(pmin, 2),
        "max":        round(pmax, 2),
        "percentile": round(pct, 1),
        "zscore":     round(z, 2),
        "pct_vs_avg": round(pct_vs, 1),
        "comment":    comment,
    }
