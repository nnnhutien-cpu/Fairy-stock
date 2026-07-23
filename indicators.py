import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ==================================================================================
# HỆ THỐNG "CÔ TIÊN" — 3 ĐƯỜNG ĐỊNH GIÁ Kijun17 / Knife1(65) / Knife2(129)
# ==================================================================================


# ------------------------------------------------------------------
# _empty_snapshot — PHẢI định nghĩa TRƯỚC market_snapshot
# ------------------------------------------------------------------
def _empty_snapshot():
    return {
        "price": 0, "change": 0, "change_pct": 0,
        "ma20": None, "ma50": None, "ma200": None,
        "trend_text": "⏳ Đang tải…", "ma20_text": "—", "ma20_alert": "info",
        "vol_today": 0, "vol_avg": 0, "vol_ratio": 0, "vol_text": "—",
        "rsi": 50, "rsi_text": "—", "rsi_color": "info",
        "macd": 0, "macd_signal": 0, "macd_cross": "—", "macd_color": "info",
        "support": 0, "resistance": 0,
    }


def market_snapshot(symbol="VNINDEX", days=250):
    """Lấy & phân tích chỉ số thị trường — dùng vnstock trực tiếp."""
    try:
        from vnstock import Vnstock
        end_date   = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        df = stock.quote.history(start=start_date, end=end_date, interval="1D")
        df = df.rename(columns={
            "time": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume"
        })
        df = df[["date", "open", "high", "low", "close", "volume"]]
    except Exception:
        try:
            df = pd.read_csv(f"data/{symbol}.csv")
        except Exception:
            return _empty_snapshot()

    if df is None or df.empty or len(df) < 30:
        return _empty_snapshot()

    df = df.sort_values("date").reset_index(drop=True)

    # ===== Moving Averages =====
    df["MA20"]  = df["close"].rolling(20).mean()
    df["MA50"]  = df["close"].rolling(50).mean()
    df["MA200"] = df["close"].rolling(200).mean()

    # ===== RSI(14) =====
    delta = df["close"].diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # ===== MACD =====
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"]   = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # ===== Volume stats =====
    df["Vol_MA20"] = df["volume"].rolling(20).mean()

    cur  = df.iloc[-1]
    prev = df.iloc[-2]

    def _nan(x):
        try:
            return x != x or x is None
        except Exception:
            return True

    # ----- Trend (MA20) -----
    if _nan(cur["MA20"]):
        trend_text = "⏳ Đang tải dữ liệu…"
        ma20_text  = "—"
        ma20_alert = "info"
    else:
        above   = cur["close"] > cur["MA20"]
        rising  = cur["MA20"] > prev["MA20"]
        crossed = (prev["close"] >= prev["MA20"]) and (not above)

        if above and rising:
            trend_text = "📈 Xu hướng tăng mạnh"
            ma20_text  = "Giá trên MA20 và MA20 đang dốc lên"
            ma20_alert = "success"
        elif above and not rising:
            trend_text = "↗️ Xu hướng tăng chậm lại"
            ma20_text  = "Giá trên MA20 nhưng MA20 đi ngang"
            ma20_alert = "info"
        elif crossed:
            trend_text = "⚠️ Vừa gãy MA20"
            ma20_text  = "Giá vừa cắt xuống dưới MA20"
            ma20_alert = "warning"
        else:
            trend_text = "📉 Xu hướng giảm"
            ma20_text  = "Giá đang dưới MA20"
            ma20_alert = "danger"

    # ----- Volume -----
    vol_today = float(cur["volume"])
    vol_avg   = float(cur["Vol_MA20"]) if not _nan(cur["Vol_MA20"]) else 0
    vol_ratio = vol_today / vol_avg if vol_avg > 0 else 0
    if vol_ratio >= 1.5:
        vol_text = f"🔥 Đột biến {vol_ratio:.1f}x trung bình 20 phiên"
    elif vol_ratio >= 1.0:
        vol_text = f"✅ Bình thường ({vol_ratio:.1f}x)"
    else:
        vol_text = f"💤 Thấp, thị trường trầm lắng ({vol_ratio:.1f}x)"

    # ----- RSI -----
    rsi = float(cur["RSI"]) if not _nan(cur["RSI"]) else 50
    if rsi >= 70:
        rsi_text, rsi_color = "🔴 Quá mua (≥70)", "danger"
    elif rsi <= 30:
        rsi_text, rsi_color = "🟢 Quá bán (≤30)", "success"
    else:
        rsi_text, rsi_color = "🟡 Trung tính", "info"

    # ----- MACD -----
    macd_cross = "Vàng" if cur["MACD"] > cur["Signal"] else "Chết"
    macd_color = "success" if macd_cross == "Vàng" else "danger"

    # ----- Hỗ trợ / Kháng cự -----
    support    = float(df["low"].tail(20).min())
    resistance = float(df["high"].tail(20).max())

    return {
        "price"      : float(cur["close"]),
        "change"     : float(cur["close"] - prev["close"]),
        "change_pct" : float((cur["close"] - prev["close"]) / prev["close"] * 100),
        "ma20"       : float(cur["MA20"])  if not _nan(cur["MA20"])  else None,
        "ma50"       : float(cur["MA50"])  if not _nan(cur["MA50"])  else None,
        "ma200"      : float(cur["MA200"]) if not _nan(cur["MA200"]) else None,
        "trend_text" : trend_text,
        "ma20_text"  : ma20_text,
        "ma20_alert" : ma20_alert,
        "vol_today"  : vol_today,
        "vol_avg"    : vol_avg,
        "vol_ratio"  : round(vol_ratio, 2),
        "vol_text"   : vol_text,
        "rsi"        : round(rsi, 2),
        "rsi_text"   : rsi_text,
        "rsi_color"  : rsi_color,
        "macd"       : round(float(cur["MACD"]), 3),
        "macd_signal": round(float(cur["Signal"]), 3),
        "macd_cross" : macd_cross,
        "macd_color" : macd_color,
        "support"    : support,
        "resistance" : resistance,
    }


# Alias an toàn — giữ tương thích nếu có file nào import tên cũ
def safe_market_snapshot(symbol="VNINDEX", days=250):
    """Alias của market_snapshot, bọc thêm try/except toàn cục."""
    try:
        return market_snapshot(symbol=symbol, days=days)
    except Exception:
        return _empty_snapshot()


@st.cache_data(show_spinner=False)
def calculate_technical_signals(
    df, ticker,
    p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26,
    k17=17, k65=65, k129=129,
    vol_spike_mult=2.5,
    hop_bich_threshold=0.0014,
):
    min_len = max(p_senkou_b + p_shift, k129) + 10
    if df is None or len(df) < min_len:
        return None

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # 1. THANH KHOẢN & MA CƠ BẢN
    df['vol_ma20'] = df['volume'].rolling(20).mean()

    # 2. RSI(14)
    delta = df['close'].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi14'] = 100 - (100 / (1 + (gain / loss)))

    # 3. MFI(14)
    typical_price  = (df['high'] + df['low'] + df['close']) / 3
    raw_money_flow = typical_price * df['volume']
    tp_diff        = typical_price.diff()
    pos_flow = raw_money_flow.where(tp_diff > 0, 0.0).rolling(14).sum()
    neg_flow = raw_money_flow.where(tp_diff < 0, 0.0).rolling(14).sum()
    money_ratio = pos_flow / neg_flow.replace(0, np.nan)
    df['mfi14'] = 100 - (100 / (1 + money_ratio))

    # 4. MÂY KUMO CỔ ĐIỂN
    df['tenkan']   = (df['high'].rolling(p_tenkan).max()   + df['low'].rolling(p_tenkan).min())   / 2
    df['kijun26']  = (df['high'].rolling(p_kijun).max()    + df['low'].rolling(p_kijun).min())    / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun26']) / 2).shift(p_shift)
    df['senkou_b'] = ((df['high'].rolling(p_senkou_b).max() + df['low'].rolling(p_senkou_b).min()) / 2).shift(p_shift)
    df['cloud_top'] = df[['senkou_a', 'senkou_b']].max(axis=1)
    df['cloud_bot'] = df[['senkou_a', 'senkou_b']].min(axis=1)

    # 5. BA ĐƯỜNG ĐỊNH GIÁ "CÔ TIÊN"
    df['kijun17']  = (df['high'].rolling(k17).max()  + df['low'].rolling(k17).min())  / 2
    df['knife65']  = (df['high'].rolling(k65).max()  + df['low'].rolling(k65).min())  / 2
    df['knife129'] = (df['high'].rolling(k129).max() + df['low'].rolling(k129).min()) / 2

    df['kijun17_up']  = df['kijun17']  > df['kijun17'].shift(5)
    df['knife65_up']  = df['knife65']  > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    # 6. MÂY NỘI BỘ
    df['fmay_top'] = df[['knife65', 'knife129']].max(axis=1)
    df['fmay_bot'] = df[['knife65', 'knife129']].min(axis=1)

    latest = df.iloc[-1]
    close  = latest['close']

    if pd.isna(latest['fmay_top']) or pd.isna(latest['knife129']):
        return None

    # 7. BỘ LỌC THANH KHOẢN >= 20 TỶ/PHIÊN
    gtgd_ty = (close * (1000 if close < 500 else 1) * latest['volume']) / 1_000_000_000
    if gtgd_ty < 20:
        return None

    # 8. VỊ TRÍ SO VỚI MÂY CỔ ĐIỂN
    if close > latest['cloud_top']:
        cloud_status = "☁️ Trên Mây"
    elif close < latest['cloud_bot']:
        cloud_status = "🌧️ Dưới Mây"
    else:
        cloud_status = "🌫️ Trong Mây"

    # 9. XU HƯỚNG
    knife_core_up   = latest['knife65'] > latest['knife129'] and latest['knife65_up'] and latest['knife129_up']
    knife_core_down = latest['knife65'] < latest['knife129'] and not latest['knife65_up'] and not latest['knife129_up']

    all3_up = (
        knife_core_up
        and latest['kijun17'] > latest['fmay_top'] and latest['kijun17_up']
        and close > latest['fmay_top']
    )
    all3_down = (
        knife_core_down
        and latest['kijun17'] < latest['fmay_bot'] and not latest['kijun17_up']
        and close < latest['fmay_bot']
    )

    end_uptrend   = close <= latest['knife129']
    end_downtrend = close >= latest['knife129']

    if all3_up and not end_uptrend:
        xu_huong = "🟢 Tăng"
    elif all3_down and not end_downtrend:
        xu_huong = "🔴 Giảm"
    else:
        xu_huong = "🟡 Sideway"

    hop_bich = abs(latest['knife65'] - latest['knife129']) / latest['knife129'] <= hop_bich_threshold

    # 10. ĐỊNH GIÁ THEO ĐƯỜNG 129
    pct_vs_129 = (close - latest['knife129']) / latest['knife129'] * 100
    if pct_vs_129 <= 0:
        dinh_gia = "📉 Rẻ (dưới/sát 129)"
    elif pct_vs_129 <= 15:
        dinh_gia = "⚖️ Hợp lý"
    else:
        dinh_gia = "📈 Đắt (mua bằng lòng tham)"

    canh_bao_mua_duoi = pct_vs_129 > 15

    # 11. KHỐI LƯỢNG
    v_ratio = latest['volume'] / latest['vol_ma20'] if latest['vol_ma20'] > 0 else 0
    flow    = "🔥 Tiền Vào Mạnh" if v_ratio >= 1.5 else ("⚡ Có Tín Hiệu" if v_ratio >= 1 else "💤 Tiền Yếu")

    gia_chiet_khau_sau = pct_vs_129 <= 5
    bat_day = "🎯 BẮT ĐÁY (Vol {:.1f}x + giá chiết khấu 129)".format(v_ratio) \
        if (gia_chiet_khau_sau and v_ratio >= vol_spike_mult) else "-"

    near_high    = close >= df['close'].rolling(20).max().iloc[-1] * 0.97
    canh_bao_dinh = near_high and v_ratio < 0.7

    # 12. TÍN HIỆU MFI/RSI
    rsi_v, mfi_v = latest['rsi14'], latest['mfi14']
    if xu_huong == "🟡 Sideway" and pd.notna(rsi_v) and pd.notna(mfi_v):
        if rsi_v <= 30 or mfi_v <= 30:
            tin_hieu_sideway = "🟢 Mua (vùng quá bán)"
        elif rsi_v >= 70 or mfi_v >= 70:
            tin_hieu_sideway = "🔴 Bán (vùng quá mua)"
        else:
            tin_hieu_sideway = "⏸️ Chờ (giữa biên độ)"
    else:
        tin_hieu_sideway = "— (đang có xu hướng, không dùng MFI/RSI)"

    # 13. TRẠNG THÁI TỔNG
    if xu_huong == "🟢 Tăng":
        trang_thai = "🟢 Tích cực"
    elif xu_huong == "🔴 Giảm":
        trang_thai = "🔴 Tiêu cực"
    else:
        trang_thai = "🟡 Trung tính"

    return {
        "Mã CP"                    : ticker,
        "Giá"                      : close,
        "GTGD (Tỷ)"               : round(gtgd_ty, 2),
        "Khối Lượng"               : int(latest['volume']),
        "KL TB 20 Phiên"           : int(latest['vol_ma20']),
        "Vol x TB20"               : round(v_ratio, 2),
        "Dòng Tiền"                : flow,
        "Xu Hướng"                 : xu_huong,
        "Ichimoku_Cloud"           : cloud_status,
        "Kijun17"                  : round(latest['kijun17'], 2),
        "Knife65"                  : round(latest['knife65'], 2),
        "Knife129"                 : round(latest['knife129'], 2),
        "Cách Knife129 (%)"        : round(pct_vs_129, 2),
        "Định Giá (129)"           : dinh_gia,
        "Hợp Bích (65≈129)"       : "✅" if hop_bich else "",
        "Cảnh Báo Mua Đuổi"       : "⚠️" if canh_bao_mua_duoi else "",
        "Cảnh Báo Tạo Đỉnh"       : "⚠️" if canh_bao_dinh else "",
        "Tín Hiệu Bắt Đáy"        : bat_day,
        "RSI14"                    : round(rsi_v, 2) if pd.notna(rsi_v) else None,
        "MFI14"                    : round(mfi_v, 2) if pd.notna(mfi_v) else None,
        "Tín Hiệu Sideway (MFI/RSI)": tin_hieu_sideway,
        "Trạng thái"               : trang_thai,
    }


# ==================================================================================
# HÀM LẤY P/E, P/B, ROE, ROA — dùng vnstock VCI financial ratio API
# Gọi: get_pe_ratio("HPG")  → dict hoặc None nếu lỗi
# ==================================================================================

@st.cache_data(ttl=3600, show_spinner=False)   # cache 1 giờ, P/E không thay đổi từng phút
def get_pe_ratio(ticker: str) -> dict | None:
    """
    Lấy các chỉ số định giá hiện tại từ vnstock VCI:
      P/E, P/B, P/S, EV/EBITDA, ROE, ROA, Dividend Yield, Market Cap
    Trả về dict với kỳ báo cáo mới nhất, hoặc None nếu không lấy được.

    Cách gọi trong Streamlit:
        val = get_pe_ratio("HPG")
        if val:
            st.metric("P/E", val["pe"])
    """
    try:
        from vnstock.explorer.vci.financial import Finance

        # Lấy ratio theo quý (mới nhất hơn so với year)
        fin = Finance(symbol=ticker.upper(), period="quarter", show_log=False)
        df  = fin.ratio(period="quarter", lang="en", dropna=True, show_log=False)

        if df is None or df.empty:
            return None

        # Lấy hàng mới nhất (đã sắp xếp desc theo kỳ bởi vnstock)
        row = df.iloc[0]

        def _safe(col, default=None):
            try:
                v = row[col]
                return round(float(v), 2) if v == v and v is not None else default
            except Exception:
                return default

        # Tìm tên cột period linh hoạt
        period_label = "—"
        for col in ["report_period", "period", "Kỳ báo cáo", "Period"]:
            if col in df.columns:
                period_label = str(row[col])
                break

        return {
            "ticker"        : ticker.upper(),
            "period"        : period_label,
            "pe"            : _safe("P/E"),
            "pb"            : _safe("P/B"),
            "ps"            : _safe("P/S"),
            "ev_ebitda"     : _safe("EV/EBITDA"),
            "roe"           : _safe("ROE (%)"),
            "roa"           : _safe("ROA (%)"),
            "div_yield"     : _safe("Dividend Yield (%)"),
            "market_cap"    : _safe("Market Cap"),
            "debt_equity"   : _safe("Debt/Equity"),
            "current_ratio" : _safe("Current Ratio"),
        }

    except Exception:
        return None


def render_valuation_metrics(ticker: str):
    """
    Render block định giá P/E trong Streamlit.
    Gọi trực tiếp trong tab_market hoặc tab_simulation.

    Ví dụ dùng:
        from indicators import render_valuation_metrics
        render_valuation_metrics("HPG")
    """
    val = get_pe_ratio(ticker)

    st.markdown(f"#### 🏷️ Định giá — {ticker.upper()}")

    if val is None:
        st.warning(f"Không lấy được chỉ số định giá cho {ticker} (API VCI cần đăng nhập hoặc mạng bị chặn).")
        return

    st.caption(f"Kỳ báo cáo gần nhất: **{val['period']}**")

    # Hàng 1: P/E · P/B · P/S · EV/EBITDA
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("P/E",       f"{val['pe']:.1f}x"       if val['pe']       else "—")
    c2.metric("P/B",       f"{val['pb']:.2f}x"       if val['pb']       else "—")
    c3.metric("P/S",       f"{val['ps']:.2f}x"       if val['ps']       else "—")
    c4.metric("EV/EBITDA", f"{val['ev_ebitda']:.1f}x" if val['ev_ebitda'] else "—")

    # Hàng 2: ROE · ROA · Div Yield · D/E
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("ROE",          f"{val['roe']:.1f}%"       if val['roe']       else "—")
    c6.metric("ROA",          f"{val['roa']:.1f}%"       if val['roa']       else "—")
    c7.metric("Div Yield",    f"{val['div_yield']:.2f}%" if val['div_yield'] else "—")
    c8.metric("D/E",          f"{val['debt_equity']:.2f}x" if val['debt_equity'] else "—")

    # Đánh giá nhanh P/E
    if val['pe']:
        if val['pe'] < 10:
            st.success(f"✅ P/E = {val['pe']:.1f}x — **Vùng hấp dẫn** (dưới 10x)")
        elif val['pe'] < 15:
            st.info(f"ℹ️ P/E = {val['pe']:.1f}x — **Hợp lý** (10–15x)")
        elif val['pe'] < 25:
            st.warning(f"⚠️ P/E = {val['pe']:.1f}x — **Đang cao** (15–25x), cần thận trọng")
        else:
            st.error(f"🚨 P/E = {val['pe']:.1f}x — **Rất đắt** (>25x), rủi ro mua đuổi")

    st.caption("⚠️ Chỉ số tính theo kỳ báo cáo gần nhất từ VCI — không phải TTM real-time.")
