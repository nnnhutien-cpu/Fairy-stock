import os
import json
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
# Dùng để nội suy P/E hiện tại từ giá VNINDEX real-time
_EPS_POINTS = {
    year: round(price / pe, 4)
    for year, (price, pe) in {
        2005: ( 307.5, 15.5), 2006: ( 751.8, 25.2), 2007: ( 927.0, 34.5),
        2008: ( 315.6, 10.8), 2009: ( 494.8, 14.1), 2010: ( 484.7, 13.2),
        2011: ( 351.6,  9.8), 2012: ( 413.7, 11.2), 2013: ( 504.6, 13.5),
        2014: ( 545.6, 12.8), 2015: ( 579.0, 12.5), 2016: ( 664.9, 13.9),
        2017: ( 984.2, 18.2), 2018: ( 892.5, 15.8), 2019: (1007.1, 16.5),
        2020: (1103.9, 16.8), 2021: (1498.3, 18.3), 2022: ( 998.7, 10.3),
        2023: (1129.9, 13.1), 2024: (1266.8, 13.9), 2025: (1300.0, 13.4),
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
#  MARKET-LEVEL P/E — không cần API key
# ============================================================

def get_current_pe(vnindex_price: "float | None" = None) -> "float | None":
    """
    Tính P/E VN-INDEX = Giá hiện tại / EPS trailing (tính theo điểm index).

    vnindex_price: giá đóng cửa VNINDEX mới nhất từ intraday_df (truyền từ main.py).
                   Hoàn toàn không gọi vnstock API (bị 403 khi không có API key).

    EPS theo điểm = Giá EOY năm trước / P/E EOY năm trước (nguồn hard-coded FiinTrade).
    """
    if vnindex_price is None or float(vnindex_price) <= 0:
        return None
    try:
        year = _dt.date.today().year
        # Ưu tiên dùng EPS năm hiện tại, fallback năm trước
        eps = _EPS_POINTS.get(year) or _EPS_POINTS.get(year - 1)
        if eps and eps > 0:
            return round(float(vnindex_price) / eps, 2)
    except Exception:
        pass
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

    if pct < 15:
        comment = (f"💎 **RẺ kỷ lục** — P/E={pe_now:.1f}x ở percentile "
                   f"{pct:.0f}%, thấp hơn TB {abs(pct_vs):.0f}%. Cơ hội tích lũy dài hạn.")
    elif pct < 30:
        comment = (f"🟢 **Vùng rẻ** — P/E={pe_now:.1f}x percentile {pct:.0f}%. "
                   f"Thị trường đang định giá hấp dẫn so với lịch sử.")
    elif pct < 70:
        comment = (f"🟡 **Hợp lý** — P/E={pe_now:.1f}x percentile {pct:.0f}%. "
                   f"Định giá cân bằng, không có tín hiệu rõ ràng.")
    elif pct < 85:
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
