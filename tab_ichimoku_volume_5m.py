# ==================================================================================
# TAB "🕯️ Tín Hiệu 5 Phút" — MUA THEO MA VOLUME + ICHIMOKU (KHUNG 5 PHÚT)
# File TÁCH RIÊNG khỏi hệ Ichimoku daily "Cô Tiên" (tab_khuyen_nghi.py) — không
# đụng vào code cũ, chỉ cộng thêm 1 tab mới.
# (Font/CSS đồng bộ với các tab khác — dùng class sb-header / sb-note / sb-stat
#  đã được inject sẵn trong main.py, không cần định nghĩa lại)
# ==================================================================================
"""
Điều kiện MUA (bắt buộc đồng thời cả 3, tính trên nến 5 phút intraday):
  1. Tenkan cắt lên Kijun                 -> xác nhận đảo chiều ngắn hạn trong phiên
  2. Giá đóng cửa nến 5' đang NẰM TRÊN mây Ichimoku (Senkou A & B) -> lọc tín hiệu
     giả khi xu hướng nền vẫn còn xấu
  3. Volume nến 5' vượt MA(Volume, N) x hệ số đột biến -> xác nhận có dòng tiền
     thật đứng sau cú cắt lên, không phải nến "khô thanh khoản"

Tích hợp vào main.py (thêm 1 tab thứ 7, KHÔNG sửa 6 tab hiện có):

    from tab_ichimoku_volume_5m import render_ichimoku_volume_tab
    ...
    tab_market, tab_screener, tab_signals, tab_recommendation, tab_suc_bat, \\
        tab_portfolio, tab_ichimoku_vol = st.tabs([
            "🌟 Thị Trường", "🔍 Lọc Cuối Ngày", "📡 Tín Hiệu (Realtime)",
            "💡 Khuyến Nghị", "🚀 Sức Bật", "💼 Danh mục", "🕯️ Tín Hiệu 5 Phút",
        ])
    ...
    with tab_ichimoku_vol:
        render_ichimoku_volume_tab(PRIORITY_TICKERS)
"""

import time
import concurrent.futures as _cf

import numpy as np
import pandas as pd
import streamlit as st

from data_loader import get_intraday_stock

SESSION_KEY_RESULT  = "ichimoku_vol_5m_result"
SESSION_KEY_ELAPSED = "ichimoku_vol_5m_elapsed"
SESSION_KEY_DIAG     = "ichimoku_vol_5m_diag"


# ─────────────────────────────────────────────────────────────
# 1. RESAMPLE 1 PHÚT -> 5 PHÚT (bỏ nến rỗng giờ nghỉ trưa/qua đêm)
# ─────────────────────────────────────────────────────────────
def _resample_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    if df_1m is None or df_1m.empty:
        return pd.DataFrame()

    d = df_1m.copy()
    d.columns = [str(c).lower().strip() for c in d.columns]
    if "time" not in d.columns or "close" not in d.columns:
        return pd.DataFrame()

    d["time"] = pd.to_datetime(d["time"])
    d = d.set_index("time").sort_index()

    ohlc = d.resample("5min", label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    })
    ohlc = ohlc.dropna(subset=["close"])

    hm = ohlc.index.strftime("%H:%M")
    in_session = ((hm >= "09:05") & (hm <= "11:30")) | ((hm >= "13:05") & (hm <= "15:00"))
    return ohlc[in_session]


# ─────────────────────────────────────────────────────────────
# 2. TÍNH ICHIMOKU + MA VOLUME TRÊN KHUNG 5' (cùng công thức rolling
#    max/min mà tab_khuyen_nghi.py đang dùng cho khung daily)
# ─────────────────────────────────────────────────────────────
def compute_ichimoku_volume_signal(
    df_1m: pd.DataFrame,
    p_tenkan: int = 9,
    p_kijun: int = 26,
    p_senkou_b: int = 52,
    p_shift: int = 26,
    vol_ma_len: int = 20,
    vol_spike_mult: float = 1.5,
):
    """Trả về dict trạng thái tại nến 5' gần nhất, hoặc None nếu thiếu dữ liệu."""
    df = _resample_5m(df_1m)
    min_bars = max(p_senkou_b + p_shift, vol_ma_len) + 2
    if df.empty or len(df) < min_bars:
        return None

    df = df.copy()
    df["tenkan"]   = (df["high"].rolling(p_tenkan).max()    + df["low"].rolling(p_tenkan).min())    / 2
    df["kijun"]    = (df["high"].rolling(p_kijun).max()     + df["low"].rolling(p_kijun).min())     / 2
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(p_shift)
    df["senkou_b"] = ((df["high"].rolling(p_senkou_b).max() + df["low"].rolling(p_senkou_b).min()) / 2).shift(p_shift)
    df["cloud_top"] = df[["senkou_a", "senkou_b"]].max(axis=1)

    df["vol_ma"]    = df["volume"].rolling(vol_ma_len).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma"].replace(0, np.nan)

    df["tenkan_cross_up"] = (df["tenkan"] > df["kijun"]) & (df["tenkan"].shift(1) <= df["kijun"].shift(1))
    df["above_cloud"]     = df["close"] > df["cloud_top"]
    df["volume_spike"]    = df["volume"] > (df["vol_ma"] * vol_spike_mult)
    df["buy_signal"]      = df["tenkan_cross_up"] & df["above_cloud"] & df["volume_spike"]

    last = df.iloc[-1]
    if pd.isna(last.get("kijun")) or pd.isna(last.get("vol_ma")):
        return None

    prev_close = df["close"].iloc[-2] if len(df) >= 2 else last["close"]
    change_pct = (last["close"] - prev_close) / prev_close * 100 if prev_close else 0.0

    return {
        "time":            df.index[-1],
        "close":           float(last["close"]),
        "change_pct":      float(change_pct),
        "volume":          float(last["volume"]),
        "vol_ratio":       float(last["vol_ratio"]) if pd.notna(last["vol_ratio"]) else 0.0,
        "buy_signal":      bool(last["buy_signal"]),
        "above_cloud":     bool(last["above_cloud"]),
        "tenkan_cross_up": bool(last["tenkan_cross_up"]),
    }


# ─────────────────────────────────────────────────────────────
# 3. QUÉT NHIỀU MÃ SONG SONG (cùng pattern ThreadPoolExecutor mà
#    main.py dùng trong execute_scan())
# ─────────────────────────────────────────────────────────────
def _scan_one(ticker: str, params: dict):
    """
    Trả về (status, res):
      status = "no_data"    -> get_intraday_stock() rỗng (nguồn dữ liệu lỗi/rate-limit)
      status = "not_enough" -> có dữ liệu nhưng chưa đủ số nến 5' tối thiểu để tính Ichimoku
      status = "ok"         -> tính được tín hiệu (res luôn có key 'buy_signal')
      status = "error"      -> exception bất ngờ khi fetch/tính
    """
    try:
        df_1m = get_intraday_stock(ticker)
        if df_1m is None or df_1m.empty:
            return "no_data", None
        res = compute_ichimoku_volume_signal(df_1m, **params)
        if res is None:
            return "not_enough", None
        res["ticker"] = ticker
        return "ok", res
    except Exception:
        return "error", None


def scan_tickers(tickers: list, params: dict, max_workers: int = 12) -> pd.DataFrame:
    results = []
    diag = {"no_data": 0, "not_enough": 0, "error": 0, "ok": 0}
    progress_bar = st.progress(0)
    status_txt = st.empty()
    total = max(len(tickers), 1)
    done = 0

    with _cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_scan_one, t, params): t for t in tickers}
        for future in _cf.as_completed(futures):
            done += 1
            status, res = future.result()
            diag[status] = diag.get(status, 0) + 1
            if status == "ok" and res is not None and res["buy_signal"]:
                results.append(res)
            progress_bar.progress(min(done / total, 1.0))
            status_txt.caption(f"Đang quét {done}/{total} mã... tìm thấy {len(results)} tín hiệu")

    progress_bar.empty()
    status_txt.empty()

    # Lưu chẩn đoán vào session_state để render_ichimoku_volume_tab() hiển thị,
    # giúp phân biệt "0 mã vì thiếu dữ liệu" và "0 mã vì đúng là chưa có tín hiệu".
    st.session_state[SESSION_KEY_DIAG] = diag

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).sort_values("vol_ratio", ascending=False)


# ─────────────────────────────────────────────────────────────
# 4. GIAO DIỆN TAB
# ─────────────────────────────────────────────────────────────
def render_ichimoku_volume_tab(tickers: list):
    st.markdown("""
    <div class="sb-header">
        <div class="sb-title">🕯️ Tín hiệu MUA — MA Volume + Ichimoku (5 phút)</div>
        <div class="sb-sub">Tenkan cắt lên Kijun · Giá trên mây · Volume vượt MA — quét trên nến 5 phút intraday</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️ Tham số chỉ báo", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        p_tenkan   = c1.number_input("Tenkan",   value=9,  step=1, min_value=3)
        p_kijun    = c2.number_input("Kijun",    value=26, step=1, min_value=5)
        p_senkou_b = c3.number_input("Senkou B", value=52, step=1, min_value=10)
        p_shift    = c4.number_input("Dịch mây", value=26, step=1, min_value=5)

        c5, c6, c7 = st.columns(3)
        vol_ma_len     = c5.number_input("Chu kỳ MA Volume",      value=20,  step=1,   min_value=5)
        vol_spike_mult = c6.number_input("Hệ số đột biến Volume", value=1.5, step=0.1, min_value=1.0)
        max_workers    = c7.number_input("Số luồng quét song song", value=12, step=1, min_value=1, max_value=32)

    st.caption(f"📋 Danh sách quét: **{len(tickers)} mã** ưu tiên thanh khoản cao (VN30 + nhóm vốn hoá lớn).")

    if st.button("🚀 QUÉT TÍN HIỆU 5 PHÚT", type="primary", use_container_width=True):
        params = dict(
            p_tenkan=int(p_tenkan), p_kijun=int(p_kijun),
            p_senkou_b=int(p_senkou_b), p_shift=int(p_shift),
            vol_ma_len=int(vol_ma_len), vol_spike_mult=float(vol_spike_mult),
        )
        t0 = time.time()
        df_result = scan_tickers(tickers, params, max_workers=int(max_workers))
        elapsed = time.time() - t0
        st.session_state[SESSION_KEY_RESULT]  = df_result
        st.session_state[SESSION_KEY_ELAPSED] = elapsed

    df_result = st.session_state.get(SESSION_KEY_RESULT)
    if df_result is None:
        st.markdown(
            '<div class="sb-note">Bấm <b>🚀 QUÉT TÍN HIỆU 5 PHÚT</b> để quét toàn bộ danh sách theo '
            'Ichimoku + MA Volume trên khung 5 phút.</div>',
            unsafe_allow_html=True,
        )
        return

    elapsed = st.session_state.get(SESSION_KEY_ELAPSED, 0)
    diag = st.session_state.get(SESSION_KEY_DIAG, {})

    if df_result.empty:
        st.info(f"⏳ Không tìm thấy mã nào đang thoả tín hiệu MUA lúc này. (quét xong trong {elapsed:.1f}s)")
        if diag:
            no_data    = diag.get("no_data", 0)
            not_enough = diag.get("not_enough", 0)
            errored    = diag.get("error", 0)
            ok         = diag.get("ok", 0)
            with st.expander("🔍 Chi tiết vì sao 0 mã (bấm để xem)", expanded=(no_data + not_enough + errored > 0)):
                d1, d2, d3, d4 = st.columns(4)
                d1.metric("❌ Không lấy được dữ liệu", no_data)
                d2.metric("⚠️ Chưa đủ nến 5'", not_enough)
                d3.metric("💥 Lỗi khi tính", errored)
                d4.metric("✅ Đủ dữ liệu, đã tính", ok)
                if no_data > 0 or not_enough > 0:
                    st.caption(
                        "👉 Nếu số **'Không lấy được dữ liệu'** hoặc **'Chưa đủ nến 5''** cao, "
                        "nghĩa là nguồn dữ liệu intraday cho các mã cổ phiếu (vnstock VCI/MSN) "
                        "đang bị rate-limit hoặc trả về không đủ số phiên gần nhất — đây là "
                        "**vấn đề nguồn dữ liệu**, không phải do không có mã nào đạt tín hiệu. "
                        "Thử quét lại sau ít phút, hoặc giảm số luồng song song (mục ⚙️ Tham số)."
                    )
                else:
                    st.caption(
                        "👉 Dữ liệu đầy đủ cho tất cả các mã — chỉ đơn giản là tại thời điểm "
                        "quét chưa có mã nào thoả cùng lúc cả 3 điều kiện (Tenkan cắt Kijun + "
                        "trên mây + Volume đột biến). Đây là hoạt động bình thường, không phải lỗi."
                    )
        return

    st.success(f"✅ Tìm thấy **{len(df_result)} mã** đang có tín hiệu MUA (5') — quét xong trong {elapsed:.1f}s")

    show_df = df_result.copy()
    show_df["time"]        = show_df["time"].dt.strftime("%H:%M")
    show_df["change_pct"]  = show_df["change_pct"].map(lambda x: f"{x:+.2f}%")
    show_df["vol_ratio"]   = show_df["vol_ratio"].map(lambda x: f"{x:.1f}x")
    show_df["volume"]      = show_df["volume"].map(lambda x: f"{x:,.0f}")
    show_df["close"]       = show_df["close"].map(lambda x: f"{x:,.2f}")
    show_df = show_df.rename(columns={
        "ticker": "Mã CP", "time": "Nến 5' lúc", "close": "Giá",
        "change_pct": "%change", "volume": "Volume", "vol_ratio": "Đột biến Vol",
    })[["Mã CP", "Nến 5' lúc", "Giá", "%change", "Volume", "Đột biến Vol"]]

    st.dataframe(show_df, use_container_width=True, hide_index=True)
    st.caption(
        "⚠️ Tín hiệu quét realtime trong phiên, không phải khuyến nghị đầu tư chính thức. "
        "Dữ liệu 1 phút gộp lại thành nến 5' nên có thể trễ ~1-2 phút so với bảng giá."
    )
