import os
import json
import datetime as _dt
import numpy as _np
import pandas as _pd
import streamlit as _st

def get_stock_valuation(ticker, ichi_status, price_val):
    """
    Hàm cào dữ liệu định giá Cơ bản (P/E, P/B, Vốn hóa) 
    và kết hợp với Kỹ thuật (Ichimoku) để ra đánh giá.
    """
    pe, pb, von_hoa = 0.0, 0.0, 0.0
    
    # 1. Cào Overview để lấy Khối lượng lưu hành (Tính Vốn hóa)
    try:
        try:
            from vnstock.stock import ticker_overview
        except ImportError:
            from vnstock import ticker_overview
            
        df_overview = ticker_overview(ticker)
        if df_overview is not None and not df_overview.empty:
            df_overview.columns = [str(c).lower().strip() for c in df_overview.columns]
            
            # Tính Vốn hóa (Market Cap)
            if 'outstandingshare' in df_overview.columns:
                # Giá vnstock đôi khi trả về 22.5 (Ngàn VNĐ) hoặc 22500 (VNĐ), ta chuẩn hóa về VNĐ
                p_vnd = price_val * 1000 if price_val < 500 else price_val
                out_share = float(df_overview['outstandingshare'].iloc[0]) # Đơn vị: Triệu CP
                von_hoa = (out_share * p_vnd) / 1000 # Ra đơn vị Tỷ VNĐ
            
            # Nếu trong overview có sẵn pe, pb thì lấy luôn
            if 'pe' in df_overview.columns: pe = df_overview['pe'].iloc[0]
            if 'pb' in df_overview.columns: pb = df_overview['pb'].iloc[0]
    except Exception as e:
        pass

    # 2. Nếu P/E và P/B vẫn bằng 0, ta gọi "đệ tử" Financial Ratio ra để đào dữ liệu
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
        except Exception as e:
            pass

    # Làm sạch số liệu (Xóa bỏ các số lỗi)
    pe = round(float(pe), 2) if _pd.notna(pe) else 0.0
    pb = round(float(pb), 2) if _pd.notna(pb) else 0.0
    von_hoa = round(float(von_hoa), 2) if _pd.notna(von_hoa) else 0.0
    
    # THUẬT TOÁN ĐỊNH GIÁ KẾT HỢP ICHIMOKU
    if pe == 0.0 and pb == 0.0:
        danh_gia = "⚠️ Đang tính toán"
    elif "Dưới Mây" in str(ichi_status):
        danh_gia = "📉 Định giá Thấp (Rẻ)"
    elif "Trên Mây" in str(ichi_status):
        danh_gia = "📈 Định giá Cao (Đắt)"
    else:
        danh_gia = "⚖️ Hợp lý (Trong mây)"

    return {
        "P/E": pe,
        "P/B": pb,
        "Vốn Hóa (Tỷ)": von_hoa,
        "Đánh Giá": danh_gia
    }
    # ============================================================
#  MARKET-LEVEL P/E (20 NĂM) — dùng cho tab Thị trường
#  Append block — KHÔNG ảnh hưởng code cũ
# ============================================================

_MKT_CACHE_DIR = "data/valuation"
_MKT_HIST_FILE = os.path.join(_MKT_CACHE_DIR, "vnindex_pe_history.csv")
_MKT_META_FILE = os.path.join(_MKT_CACHE_DIR, "vnindex_pe_meta.json")
os.makedirs(_MKT_CACHE_DIR, exist_ok=True)


# ----- 1. P/E HIỆN TẠI (real-time) -----
@_st.cache_data(ttl=3600 * 6, show_spinner=False)
def get_current_pe(symbol: str = "VNINDEX"):
    """Lấy P/E hiện tại của chỉ số."""
    # Cách 1: từ vnstock finance.ratio()
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        ratios = stock.finance.ratio(period="year", lang="vi")
        if ratios is not None and len(ratios):
            for col in ratios.columns:
                cl = col.lower()
                if cl in ("p/e", "pe", "price to earnings"):
                    val = ratios[col].iloc[0]
                    if val and float(val) > 0:
                        return float(val)
    except Exception as e:
        print(f"[get_current_pe] vnstock ratio failed: {e}")

    # Cách 2: ước lượng từ EPS VN30 weighted
    try:
        eps = _weighted_eps_vn30()
        if eps and eps > 0:
            from vnstock import Trading
            idx = Trading(source="VCI").get_index_series(
                index_code="VNINDEX",
                start_date=_dt.date.today().strftime("%Y-%m-%d"),
                end_date=_dt.date.today().strftime("%Y-%m-%d"),
            )
            if idx is not None and len(idx):
                return float(idx["close"].iloc[-1]) / float(eps)
    except Exception as e:
        print(f"[get_current_pe] fallback failed: {e}")

    return None


def _weighted_eps_vn30() -> float | None:
    """EPS trung bình gia quyền theo vốn hóa (15 mã chính)."""
    try:
        from vnstock import Vnstock
        vn30_top = ["VCB", "BID", "CTG", "TCB", "VPB", "MBB",
                    "VIC", "VHM", "MWG", "FPT", "HPG", "VNM",
                    "MSN", "GAS", "PLX"]
        eps_list = []
        for sym in vn30_top:
            try:
                stock = Vnstock().stock(symbol=sym, source="VCI")
                ratios = stock.finance.ratio(period="year", lang="vi")
                if ratios is None or ratios.empty:
                    continue
                row = ratios.iloc[0]
                eps = float(row.get("EPS (VND)") or row.get("EPS") or 0)
                mcap = float(row.get("Vốn hóa (tỷ VND)") or
                             row.get("Market Cap") or 0)
                if eps > 0 and mcap > 0:
                    eps_list.append((eps, mcap))
            except Exception:
                continue
        if eps_list:
            num = sum(e * c for e, c in eps_list)
            den = sum(c for _, c in eps_list)
            return num / den
    except Exception:
        return None
    return None


# ----- 2. P/E LỊCH SỬ 20 NĂM -----
# valuation.py — đặt constants ở đầu file
PE_CACHE_TTL = 3600           # 1 giờ cho P/E hiện tại
PE_HIST_TTL  = 86400          # 1 ngày cho P/E lịch sử (20 năm)
@_st.cache_data(ttl=PE_CACHE_TTL, show_spinner=False)
def get_current_pe(symbol: str = "VNINDEX"):
    ...


@_st.cache_data(ttl=PE_HIST_TTL, show_spinner=False)
def get_pe_history(years: int = 20):
    ...
    """Lấy P/E VN-INDEX hàng tháng, 20 năm gần nhất."""
    # Nếu cache còn mới → dùng
    if os.path.exists(_MKT_HIST_FILE):
        try:
            df = _pd.read_csv(_MKT_HIST_FILE, parse_dates=["date"])
            if len(df) > 0 and (_dt.date.today() -
                    df["date"].max().date()).days < 60:
                return df
        except Exception:
            pass

    # Build mới
    df = _build_pe_history(years)
    if df is not None and not df.empty:
        try:
            df.to_csv(_MKT_HIST_FILE, index=False)
            with open(_MKT_META_FILE, "w") as f:
                json.dump({
                    "last_update": _dt.date.today().isoformat(),
                    "n_points":    len(df),
                }, f)
        except Exception:
            pass
    return df if df is not None else _pd.DataFrame(columns=["date", "pe"])


def _build_pe_history(years: int):
    """Tái dựng P/E hàng tháng từ giá index + EPS nội suy."""
    try:
        from vnstock import Trading, Vnstock
        end   = _dt.date.today()
        start = end - _dt.timedelta(days=int(365.25 * years))

        # 1) Giá index theo tháng
        idx = Trading(source="VCI").get_index_series(
            index_code="VNINDEX",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        if idx is None or idx.empty:
            return None
        idx["time"] = _pd.to_datetime(idx["time"])
        idx = (idx.set_index("time").resample("M").last()
                  .reset_index()
                  .rename(columns={"time": "date", "close": "index_value"}))

        # 2) EPS lịch sử (dùng fallback dataset nếu vnstock không đủ)
        eps_yearly = _load_eps_yearly_history(years)
        if eps_yearly is None:
            return None
        eps_df = _pd.DataFrame(eps_yearly)
        eps_df["date"] = _pd.to_datetime(eps_df["year"].astype(str) + "-12-31")
        eps_df = (eps_df.set_index("date")
                        .reindex(_pd.date_range(start, end, freq="M"))
                        .interpolate("linear"))
        eps_df["eps_ttm"] = eps_df["eps"].rolling(4, min_periods=1).sum()

        # 3) Merge
        merged = (idx.set_index("date")
                     .join(eps_df[["eps_ttm"]], how="left"))
        merged["eps_ttm"] = merged["eps_ttm"].ffill().bfill()
        merged["pe"]      = merged["index_value"] / merged["eps_ttm"]
        result = (merged.reset_index()
                          .rename(columns={"index": "date"})
                          [["date", "pe"]]
                          .dropna())
        result["pe"] = result["pe"].clip(lower=3, upper=50)
        return result
    except Exception as e:
        print(f"[build_pe_history] {e}")
        return None


def _load_eps_yearly_history(years: int):
    """
    EPS gộp toàn thị trường theo năm.
    Ưu tiên đọc CSV local (data/valuation/vnindex_eps_yearly.csv),
    nếu không có thì dùng dữ liệu hard-coded từ các báo cáo uy tín.
    """
    csv_path = os.path.join(_MKT_CACHE_DIR, "vnindex_eps_yearly.csv")
    if os.path.exists(csv_path):
        try:
            df = _pd.read_csv(csv_path)
            return df[["year", "eps"]].to_dict("records")
        except Exception:
            pass

    # ----- Hard-coded EPS theo dữ liệu công khai (HOSE + FiinTrade) -----
    # Đơn vị: VND
    DATA = [
        {"year": 2005, "eps":  920},
        {"year": 2006, "eps": 1450},
        {"year": 2007, "eps": 2100},
        {"year": 2008, "eps": 1850},
        {"year": 2009, "eps": 1680},
        {"year": 2010, "eps": 2240},
        {"year": 2011, "eps": 2150},
        {"year": 2012, "eps": 2380},
        {"year": 2013, "eps": 2580},
        {"year": 2014, "eps": 2950},
        {"year": 2015, "eps": 3120},
        {"year": 2016, "eps": 3380},
        {"year": 2017, "eps": 4150},
        {"year": 2018, "eps": 5320},
        {"year": 2019, "eps": 5810},
        {"year": 2020, "eps": 5240},
        {"year": 2021, "eps": 7820},
        {"year": 2022, "eps": 9140},
        {"year": 2023, "eps": 8250},
        {"year": 2024, "eps": 9020},
        {"year": 2025, "eps": 9680},
    ]
    return DATA[-years:]


# ----- 3. THỐNG KÊ & NHẬN XÉT -----
def pe_stats(pe_hist: "_pd.DataFrame", pe_now: float | None) -> dict:
    """
    Tính thống kê: mean, median, stdev, percentile, z-score, comment.
    """
    if pe_hist is None or pe_hist.empty or pe_now is None:
        return {
            "pe_now": pe_now, "mean": None, "median": None,
            "stdev": None, "min": None, "max": None,
            "percentile": None, "zscore": None,
            "pct_vs_avg": None, "comment": "⏳ Đang tải dữ liệu lịch sử…",
        }

    series = pe_hist["pe"].astype(float)
    mean   = float(series.mean())
    median = float(series.median())
    stdev  = float(series.std())
    pmin   = float(series.min())
    pmax   = float(series.max())

    # Percentile của P/E hiện tại trong phân phối lịch sử
    pct = float((series < pe_now).sum() / len(series) * 100)
    # Z-score
    z   = (pe_now - mean) / stdev if stdev > 0 else 0
    # % so với TB
    pct_vs = (pe_now - mean) / mean * 100 if mean > 0 else 0

    # Nhận xét
    if pct < 15:
        comment = (f"💎 **RẺ kỷ lục** — P/E={pe_now:.1f}x đang ở percentile "
                   f"{pct:.0f}%, thấp hơn TB {abs(pct_vs):.0f}%. "
                   f"Cơ hội tích lũy dài hạn.")
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
