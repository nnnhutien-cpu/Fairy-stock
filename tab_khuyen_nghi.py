# ==================================================================================
# TAB KHUYẾN NGHỊ MUA / BÁN — Hệ thống "Cô Tiên"
# (Font đồng bộ với tab Sức Bật — dùng sb-header / lk-card CSS class từ main.py)
# ==================================================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_loader import get_data_freshness, get_expected_latest_trading_date, get_all_tickers
import ui_kit

KIET_CUNG_RATIO = 0.5


def _compute_recommendation_data(df, ticker, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    df['tenkan'] = (df['high'].rolling(p_tenkan).max() + df['low'].rolling(p_tenkan).min()) / 2
    df['kijun26'] = (df['high'].rolling(p_kijun).max() + df['low'].rolling(p_kijun).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun26']) / 2).shift(p_shift)
    df['senkou_b'] = ((df['high'].rolling(p_senkou_b).max() + df['low'].rolling(p_senkou_b).min()) / 2).shift(p_shift)

    df['kijun17'] = (df['high'].rolling(17).max() + df['low'].rolling(17).min()) / 2
    df['knife65'] = (df['high'].rolling(65).max() + df['low'].rolling(65).min()) / 2
    df['knife129'] = (df['high'].rolling(129).max() + df['low'].rolling(129).min()) / 2

    df['kijun17_up'] = df['kijun17'] > df['kijun17'].shift(5)
    df['knife65_up'] = df['knife65'] > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    df['fmay_top'] = df[['knife65', 'knife129']].max(axis=1)
    df['fmay_bot'] = df[['knife65', 'knife129']].min(axis=1)

    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi14'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ma20_trend'] = df['vol_ma20'] - df['vol_ma20'].shift(3)
    df['pct_vs_129'] = (df['close'] - df['knife129']) / df['knife129'] * 100

    latest = df.iloc[-1]
    close = latest['close']

    knife_core_up = (
        latest['knife65'] > latest['knife129']
        and bool(latest['knife65_up'])
        and bool(latest['knife129_up'])
    )
    knife_core_down = (
        latest['knife65'] < latest['knife129']
        and not bool(latest['knife65_up'])
        and not bool(latest['knife129_up'])
    )
    fmay_top = latest['fmay_top']
    fmay_bot = latest['fmay_bot']

    all3_up = (
        knife_core_up
        and latest['kijun17'] > fmay_top and bool(latest['kijun17_up'])
        and close > fmay_top
    )
    all3_down = (
        knife_core_down
        and latest['kijun17'] < fmay_bot and not bool(latest['kijun17_up'])
        and close < fmay_bot
    )

    if all3_up and close > latest['knife129']:
        xu_huong = "TANG"
    elif all3_down and close < latest['knife129']:
        xu_huong = "GIAM"
    else:
        xu_huong = "SIDEWAY"

    pct_vs_129 = latest['pct_vs_129']
    v_ratio = latest['volume'] / latest['vol_ma20'] if latest['vol_ma20'] > 0 else 0
    rsi = latest['rsi14']
    vol_ma20_trend = latest['vol_ma20_trend']
    kiet_cung = v_ratio < KIET_CUNG_RATIO

    ly_do = []

    if xu_huong == "TANG":
        if pct_vs_129 <= 5 and v_ratio >= 2.0:
            khuyen_nghi = "🟢 MUA MẠNH (30%)"
            mo_ta = "Xu hướng tăng, giá chiết khấu sát Knife129, dòng tiền đột biến. Giải ngân 30% vốn."
        elif pct_vs_129 <= 15 and v_ratio >= 1.2:
            khuyen_nghi = "🟢 MUA (20%)"
            mo_ta = "Xu hướng tăng, giá hợp lý, dòng tiền tốt. Giải ngân 20% vốn."
        elif pct_vs_129 > 15:
            khuyen_nghi = "⏸️ GIỮ / CHỜ"
            mo_ta = "Xu hướng tăng nhưng giá đã đi xa Knife129, tránh mua đuổi."
            ly_do.append("⚠️ Cảnh báo mua đuổi: giá cách Knife129 >{:.1f}%".format(pct_vs_129))
        else:
            khuyen_nghi = "⏸️ GIỮ"
            mo_ta = "Xu hướng tăng, chưa có tín hiệu đặc biệt. Giữ CP, không mua thêm khi chưa có vol."

    elif xu_huong == "SIDEWAY":
        rsi_qua_ban = pd.notna(rsi) and rsi <= 32
        vol_nhich_len = vol_ma20_trend > 0
        gia_duoi_129 = pct_vs_129 <= 0

        if kiet_cung and rsi_qua_ban and vol_nhich_len and gia_duoi_129:
            khuyen_nghi = "🔵 MUA THĂM DÒ (10%)"
            mo_ta = "Sideway vùng đáy: thanh khoản kiệt (<50% MA20), RSI thấp, vol MA20 đang nhích lên — dấu hiệu cạn cung. Giải ngân 10% vốn."
            ly_do.append(f"📊 Vol chỉ {v_ratio:.2f}x MA20 (< {KIET_CUNG_RATIO:.0%}) → kiệt cung")
            ly_do.append(f"📉 RSI = {rsi:.1f} → vùng quá bán")
            ly_do.append(f"📈 Vol MA20 đang nhích lên (+{vol_ma20_trend:,.0f} cp) → tích lũy")
            ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → chiết khấu")
        elif (kiet_cung or rsi_qua_ban) and gia_duoi_129:
            khuyen_nghi = "🔵 MUA THĂM DÒ (5%)"
            if kiet_cung and not rsi_qua_ban:
                mo_ta = "Sideway: thanh khoản kiệt (<50% MA20), giá dưới Knife129 — dấu hiệu cạn cung. Giải ngân 5% vốn."
                ly_do.append(f"📊 Vol chỉ {v_ratio:.2f}x MA20 (< {KIET_CUNG_RATIO:.0%}) → kiệt cung")
                ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → chiết khấu")
            elif rsi_qua_ban and not kiet_cung:
                mo_ta = "Sideway quá bán, giá dưới Knife129. Chưa có xác nhận vol — chỉ thăm dò nhỏ. Giải ngân 5% vốn."
                ly_do.append(f"📉 RSI = {rsi:.1f} → quá bán")
                ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → chiết khấu")
            else:
                mo_ta = "Sideway: kiệt cung + RSI thấp + giá dưới Knife129. Giải ngân 5% vốn."
                ly_do.append(f"📊 Vol chỉ {v_ratio:.2f}x MA20 (< {KIET_CUNG_RATIO:.0%}) → kiệt cung")
                ly_do.append(f"📉 RSI = {rsi:.1f} → quá bán")
                ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → chiết khấu")
        elif pd.notna(rsi) and rsi >= 68:
            khuyen_nghi = "🔴 BÁN MỘT PHẦN"
            mo_ta = "Sideway nhưng RSI tiệm cận vùng quá mua. Chốt một phần nếu đang có lợi nhuận."
            ly_do.append(f"📈 RSI = {rsi:.1f} → tiệm cận quá mua")
        else:
            khuyen_nghi = "⏸️ CHỜ"
            mo_ta = "Sideway không rõ tín hiệu. Chờ xác nhận xu hướng từ Knife65/Knife129."

    else:  # GIAM
        gia_re = pct_vs_129 <= -10

        if kiet_cung and gia_re:
            khuyen_nghi = "🟡 MUA THĂM DÒ (Kiệt Cung, 5%)"
            mo_ta = "Đang giảm nhưng thanh khoản cạn kiệt (<50% MA20) + giá đã chiết khấu sâu so Knife129 — dấu hiệu bên bán cạn lực, thăm dò nhỏ. Giải ngân 5% vốn."
            ly_do.append(f"📊 Vol chỉ {v_ratio:.2f}x MA20 (< {KIET_CUNG_RATIO:.0%}) → kiệt cung, cạn nguồn cung bán ra")
            ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → định giá rẻ")
            ly_do.append("⚠️ Xu hướng vẫn đang GIẢM — chỉ thăm dò nhỏ, không giải ngân lớn")
        elif close < latest['knife129'] and v_ratio >= 2.5 and gia_re:
            khuyen_nghi = "🟡 BẮT ĐÁY CẨN THẬN (Vol Đột Biến, 10%)"
            mo_ta = "Giảm sâu, vol đột biến — có thể là phiên xả hàng cuối/cạn cung đối ứng, thăm dò. Giải ngân 10% vốn."
            ly_do.append(f"⚠️ Xu hướng vẫn GIẢM — chỉ thăm dò 10%")
            ly_do.append(f"📊 Vol đột biến {v_ratio:.2f}x MA20 → có thể là phiên xả cuối")
            ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → chiết khấu sâu")
        else:
            khuyen_nghi = "🔴 BÁN / TRÁNH"
            mo_ta = "Xu hướng giảm rõ ràng. Không nên giữ hoặc mua mới."

    near_high = close >= df['close'].rolling(20).max().iloc[-1] * 0.97
    if near_high and v_ratio < 0.7 and xu_huong == "TANG":
        ly_do.append("⚠️ Giá gần đỉnh 20 phiên nhưng vol yếu → cảnh báo tạo đỉnh, tránh mua đuổi")
        if "MUA" in khuyen_nghi:
            khuyen_nghi = "⏸️ GIỮ / CHỜ"

    return {
        "df": df,
        "latest": latest,
        "xu_huong": xu_huong,
        "khuyen_nghi": khuyen_nghi,
        "mo_ta": mo_ta,
        "ly_do": ly_do,
        "pct_vs_129": pct_vs_129,
        "v_ratio": v_ratio,
        "rsi": rsi,
        "vol_ma20_trend": vol_ma20_trend,
        "kiet_cung": kiet_cung,
        "close": latest['close'],
        "ticker": ticker,
    }


def render_recommendation_tab(get_stock_data_fn, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    ui_kit.page_header("💡 Khuyến Nghị MUA / BÁN — Hệ Thống Cô Tiên",
                       "Kijun17 / Knife65 / Knife129 + Volume MA20 + RSI14 (Sideway) + Kiệt Cung (<50% MA20)")

    try:
        all_codes = sorted(set(get_all_tickers("all")))
    except Exception:
        all_codes = []
    default = st.session_state.get("rec_last_ticker", "PVT")
    col_input, col_refresh = st.columns([4, 1], vertical_alignment="bottom")
    with col_input:
        rec_ticker = st.selectbox(
            "Mã cổ phiếu", options=all_codes or [default],
            index=(all_codes.index(default) if default in all_codes else 0) if all_codes else 0,
            accept_new_options=True, key="rec_ticker_select",
            placeholder="Gõ mã, ví dụ HPG, FPT, PVT…",
        )
        rec_ticker = str(rec_ticker or "").upper().strip()
    with col_refresh:
        refresh_btn = st.button("🔄 Làm mới dữ liệu", width="stretch",
                                help="Xoá cache và tải lại dữ liệu mới nhất cho mã này.")
    # Chọn mã là phân tích luôn (không cần bấm thêm nút) — kết quả giữ trong phiên làm việc
    run_btn = bool(rec_ticker) and rec_ticker != st.session_state.get("rec_last_ticker")
    if rec_ticker:
        st.session_state["rec_last_ticker"] = rec_ticker

    if not rec_ticker:
        st.info("Nhập mã cổ phiếu và bấm PHÂN TÍCH.")
        return

    if refresh_btn:
        try:
            get_stock_data_fn.clear()
        except Exception:
            pass
        st.session_state.pop(f"rec_data_{rec_ticker}", None)

    # Load dữ liệu (cache session — không gọi lại API nếu đã có)
    if run_btn or refresh_btn or f"rec_data_{rec_ticker}" not in st.session_state:
        with st.spinner(f"Đang tải dữ liệu {rec_ticker}..."):
            df_raw = get_stock_data_fn(rec_ticker, days_back=300)

        if df_raw is None or df_raw.empty:
            st.error(f"⚠️ Không lấy được dữ liệu cho mã **{rec_ticker}**. Kiểm tra lại mã hoặc API.")
            return

        result = _compute_recommendation_data(df_raw, rec_ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
        st.session_state[f"rec_data_{rec_ticker}"] = result
    else:
        result = st.session_state[f"rec_data_{rec_ticker}"]

    df = result["df"]
    latest = result["latest"]
    ticker = result["ticker"]
    close = result["close"]
    khuyen_nghi = result["khuyen_nghi"]
    mo_ta = result["mo_ta"]
    ly_do = result["ly_do"]
    pct_vs_129 = result["pct_vs_129"]
    v_ratio = result["v_ratio"]
    rsi = result["rsi"]
    vol_ma20_trend = result["vol_ma20_trend"]
    kiet_cung = result.get("kiet_cung", False)
    xu_huong_label = {"TANG": "🟢 Xu hướng TĂNG", "GIAM": "🔴 Xu hướng GIẢM", "SIDEWAY": "🟡 SIDEWAY"}.get(result["xu_huong"], "—")

    # Cảnh báo dữ liệu chậm
    freshness = get_data_freshness(df)
    if freshness["is_stale"] and freshness["latest_date"] is not None:
        lag = freshness["lag_days"]
        st.warning(
            f"⏳ Dữ liệu **{ticker}** đang chậm **{lag} ngày** so với phiên gần nhất "
            f"(mới nhất: **{freshness['latest_date']:%d/%m/%Y}**, kỳ vọng: "
            f"**{freshness['expected_date']:%d/%m/%Y}** — phiên đóng cửa 15h, cập nhật xong lúc 17h). "
            "Bấm **🔄 Làm mới** ở trên để cào lại dữ liệu sống mới nhất; khuyến nghị bên dưới "
            "có thể chưa phản ánh đúng phiên gần nhất."
        )

    # ── Panel khuyến nghị (dùng lk-card class đồng bộ CSS) ──────────────────
    tone = [("MUA MẠNH", ui_kit.UP), ("MUA THĂM DÒ", "#60a5fa"), ("MUA", ui_kit.UP), ("BẮT ĐÁY", ui_kit.WARN),
            ("BÁN MỘT PHẦN", "#f97316"), ("BÁN", ui_kit.DOWN), ("TRÁNH", ui_kit.DOWN),
            ("GIỮ", ui_kit.MUTED), ("CHỜ", ui_kit.MUTED)]
    kn_color = next((c for k, c in tone if k in khuyen_nghi.upper()), ui_kit.MUTED)

    st.markdown(f"""
    <div class="lk-card" style="border-left:4px solid {kn_color};">
        <div class="lk-label">Khuyến nghị cho {ticker} · giá {close:,.2f}</div>
        <div style="font-size:1.6rem;font-weight:800;color:{kn_color};margin-top:4px;">{khuyen_nghi}</div>
        <div style="font-size:0.92rem;color:#dcd6ec;margin-top:6px;">{mo_ta}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Số liệu nhanh ────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "📅 Ngày dữ liệu",
        str(df.iloc[-1].get('time', df.index[-1]))[:10] if 'time' in df.columns else str(df.index[-1])[:10],
        "✅ Mới nhất" if not freshness["is_stale"] else f"⏳ Chậm {freshness['lag_days']} ngày",
        delta_color="off",
    )
    col2.metric("💰 Giá đóng cửa", f"{close:,.2f}")
    col3.metric("📊 Xu hướng", xu_huong_label)
    col4.metric("📏 Cách Knife129", f"{pct_vs_129:+.2f}%")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric(
        "📦 Vol / MA20",
        f"{v_ratio:.2f}x",
        "🔻 Kiệt cung (<50%)" if kiet_cung else None,
        help="< 50% = kiệt cung | 1-1.5x = bình thường | > 1.5x = đột biến"
    )
    col6.metric("📈 RSI14", f"{rsi:.1f}" if pd.notna(rsi) else "—")
    col7.metric("📈 Vol MA20 (trend)", "⬆️ Nhích lên" if vol_ma20_trend > 0 else "⬇️ Giảm dần")
    col8.metric("🏹 Knife129", f"{latest['knife129']:,.2f}")

    if ly_do:
        st.markdown('<div class="lk-section">📋 Các tín hiệu chính</div>', unsafe_allow_html=True)
        for ld in ly_do:
            st.markdown(f"- {ld}")

    # ── 3 Đường định giá ─────────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="lk-section">📐 3 Đường Định Giá Cô Tiên</div>', unsafe_allow_html=True)
    d3_col1, d3_col2, d3_col3 = st.columns(3)
    d3_col1.metric("Kijun17 (nhanh)", f"{latest['kijun17']:,.2f}",
                   "⬆️ Đang lên" if latest['kijun17_up'] else "⬇️ Đang xuống")
    d3_col2.metric("Knife65 (trung)", f"{latest['knife65']:,.2f}",
                   "⬆️ Đang lên" if latest['knife65_up'] else "⬇️ Đang xuống")
    d3_col3.metric("Knife129 (quan trọng nhất)", f"{latest['knife129']:,.2f}",
                   "⬆️ Đang lên" if latest['knife129_up'] else "⬇️ Đang xuống")

    # ── Biểu đồ ──────────────────────────────────────────────────────────────
    st.divider()
    st.markdown(f'<div class="lk-section">📊 Biểu Đồ Phân Tích: {ticker} (100 phiên gần nhất)</div>', unsafe_allow_html=True)

    plot_df = df.tail(120).copy()
    if 'time' in plot_df.columns:
        plot_df['x'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
    else:
        plot_df['x'] = plot_df.index.astype(str)
    plot_df.set_index('x', inplace=True)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=[0.6, 0.25, 0.15],
        subplot_titles=["Giá & 3 Đường Cô Tiên", "Volume vs MA20", "RSI14"]
    )

    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df['open'], high=plot_df['high'],
        low=plot_df['low'], close=plot_df['close'],
        increasing_line_color=ui_kit.UP, increasing_fillcolor=ui_kit.UP,
        decreasing_line_color=ui_kit.DOWN, decreasing_fillcolor=ui_kit.DOWN,
        name='Giá', showlegend=False
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['senkou_a'],
        line=dict(color='rgba(0,200,83,0.3)', width=1), name='Senkou A', showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['senkou_b'],
        line=dict(color='rgba(255,23,68,0.3)', width=1),
        fill='tonexty', fillcolor='rgba(128,128,128,0.1)', name='Mây Kumo', showlegend=True
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['kijun17'],
        line=dict(color=ui_kit.SERIES[0], width=1.5, dash='dot'), name='Kijun17'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['knife65'],
        line=dict(color=ui_kit.SERIES[3], width=2, dash='dash'), name='Knife65'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['knife129'],
        line=dict(color=ui_kit.SERIES[4], width=2.5), name='Knife129 ★'
    ), row=1, col=1)

    vol_colors = ['rgba(34,197,94,.6)' if plot_df['close'].iloc[i] >= plot_df['open'].iloc[i] else 'rgba(239,68,68,.6)'
                  for i in range(len(plot_df))]
    fig.add_trace(go.Bar(
        x=plot_df.index, y=plot_df['volume'],
        marker_color=vol_colors, name='Volume', showlegend=False
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['vol_ma20'],
        line=dict(color=ui_kit.SERIES[1], width=2, shape='spline'), name='Vol MA20'
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['vol_ma20'] * KIET_CUNG_RATIO,
        line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'),
        name=f'{KIET_CUNG_RATIO:.0%} MA20 (Kiệt cung)'
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['rsi14'],
        line=dict(color=ui_kit.SERIES[5], width=1.5), name='RSI14'
    ), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,68,68,0.5)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,200,83,0.5)", row=3, col=1)
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(200,200,200,0.05)", row=3, col=1)

    ui_kit.style_fig(fig, 720, dates=False)
    fig.update_xaxes(type="category", nticks=8)
    ui_kit.plot(fig)

    with st.expander("📖 Hướng dẫn đọc khuyến nghị Cô Tiên"):
        st.markdown(f"""
**Cách hệ thống ra quyết định:**

| Khuyến nghị | Điều kiện | Tỷ trọng |
|---|---|---|
| 🟢 **MUA MẠNH** | Xu hướng TĂNG + Giá ≤5% trên Knife129 + Vol đột biến ≥ 2x MA20 | **30%** |
| 🟢 **MUA** | Xu hướng TĂNG + Giá hợp lý (≤15% trên Knife129) + Vol ≥ 1.2x MA20 | **20%** |
| 🔵 **MUA THĂM DÒ (10%)** | Sideway + Kiệt cung (Vol < {KIET_CUNG_RATIO:.0%} MA20) + RSI ≤ 32 + Vol MA20 đang nhích lên + Giá dưới Knife129 | **10%** |
| 🔵 **MUA THĂM DÒ (5%)** | Sideway + (Kiệt cung **HOẶC** RSI ≤ 32) + Giá dưới Knife129 | **5%** |
| 🟡 **MUA THĂM DÒ (Kiệt Cung, 5%)** | Đang GIẢM + Vol < {KIET_CUNG_RATIO:.0%} MA20 (bên bán cạn lực) + Giá chiết khấu sâu (>10% dưới Knife129) | **5%** |
| 🟡 **BẮT ĐÁY CẨN THẬN (Vol Đột Biến, 10%)** | Đang GIẢM + Vol đột biến ≥ 2.5x MA20 (có thể là phiên xả cuối) + Giá chiết khấu sâu | **10%** |
| ⏸️ **GIỮ** | Xu hướng TĂNG nhưng chưa có tín hiệu vol, hoặc giá đã đi xa | — |
| ⏸️ **CHỜ** | Sideway không rõ tín hiệu, chờ Knife65/129 xác nhận | — |
| 🔴 **BÁN MỘT PHẦN** | RSI tiệm cận quá mua trong Sideway, hoặc cảnh báo tạo đỉnh | — |
| 🔴 **BÁN / TRÁNH** | Xu hướng GIẢM rõ ràng, không có tín hiệu kiệt cung hay bắt đáy | — |

**Knife129 là đường quan trọng nhất:**
- Giá dưới Knife129 → vùng chiết khấu, xem xét mua
- Giá vượt Knife129 + 15% → cảnh báo mua đuổi
- Giá cắt xuống Knife129 → tín hiệu kết thúc xu hướng tăng
        """)
