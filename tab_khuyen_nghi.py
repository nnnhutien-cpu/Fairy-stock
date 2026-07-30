# ==================================================================================
# TAB KHUYẾN NGHỊ MUA / BÁN — Hệ thống "Cô Tiên"
# Dán đoạn code này vào main.py, thêm tab vào dòng st.tabs([...])
#
# Logic khuyến nghị dựa 100% trên:
#   - 3 đường: Kijun17 / Knife65 / Knife129
#   - Volume vs MA20 (tỷ lệ và xu hướng tăng/giảm)
#   - RSI14 (chỉ dùng khi Sideway — đúng triết lý Cô Tiên)
#   - Vị trí giá so với Knife129 (định giá)
# ==================================================================================

# ---- Thêm vào dòng st.tabs ở main.py: ----
# tab_market, tab_screener, tab_simulation, tab_backtest, tab_reports, tab_recommendation = st.tabs([
#     "🌟 Thị Trường", "🔍 Bộ Lọc", "🔮 Mô Phỏng", "🛠️ Backtest", "📑 Báo Cáo", "🎯 Khuyến Nghị"
# ])

# ---- Paste đoạn dưới vào cuối main.py ----

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _compute_recommendation_data(df, ticker, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """
    Tính toán đầy đủ dữ liệu kỹ thuật Cô Tiên cho tab Khuyến nghị.
    Trả về dict chứa: df có đủ cột, latest row, các cờ phân tích.
    """
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # --- Ichimoku cổ điển (dùng vẽ biểu đồ) ---
    df['tenkan'] = (df['high'].rolling(p_tenkan).max() + df['low'].rolling(p_tenkan).min()) / 2
    df['kijun26'] = (df['high'].rolling(p_kijun).max() + df['low'].rolling(p_kijun).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun26']) / 2).shift(p_shift)
    df['senkou_b'] = ((df['high'].rolling(p_senkou_b).max() + df['low'].rolling(p_senkou_b).min()) / 2).shift(p_shift)

    # --- Ba đường Cô Tiên ---
    df['kijun17'] = (df['high'].rolling(17).max() + df['low'].rolling(17).min()) / 2
    df['knife65'] = (df['high'].rolling(65).max() + df['low'].rolling(65).min()) / 2
    df['knife129'] = (df['high'].rolling(129).max() + df['low'].rolling(129).min()) / 2

    # Hướng đi (5 phiên)
    df['kijun17_up'] = df['kijun17'] > df['kijun17'].shift(5)
    df['knife65_up'] = df['knife65'] > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    # Mây nội bộ Cô Tiên
    df['fmay_top'] = df[['knife65', 'knife129']].max(axis=1)
    df['fmay_bot'] = df[['knife65', 'knife129']].min(axis=1)

    # RSI14
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi14'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    # Volume
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    # Xu hướng vol_ma20 (3 phiên — tăng dần hay giảm dần)
    df['vol_ma20_trend'] = df['vol_ma20'] - df['vol_ma20'].shift(3)

    # Khoảng cách giá vs Knife129
    df['pct_vs_129'] = (df['close'] - df['knife129']) / df['knife129'] * 100

    latest = df.iloc[-1]
    close = latest['close']

    # --- Xu hướng tổng ---
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
    vol_ma20_trend = latest['vol_ma20_trend']  # > 0 = vol đang nhích lên

    # --- LOGIC KHUYẾN NGHỊ CÔ TIÊN ---
    # Ưu tiên từ mạnh -> yếu

    ly_do = []

    if xu_huong == "TANG":
        if pct_vs_129 <= 5 and v_ratio >= 2.0:
            khuyen_nghi = "🟢 MUA MẠNH"
            mo_ta = "Xu hướng tăng, giá chiết khấu sát Knife129, dòng tiền đột biến."
        elif pct_vs_129 <= 15 and v_ratio >= 1.2:
            khuyen_nghi = "🟢 MUA"
            mo_ta = "Xu hướng tăng, giá hợp lý, dòng tiền tốt."
        elif pct_vs_129 > 15:
            khuyen_nghi = "⏸️ GIỮ / CHỜ"
            mo_ta = "Xu hướng tăng nhưng giá đã đi xa Knife129, tránh mua đuổi."
            ly_do.append("⚠️ Cảnh báo mua đuổi: giá cách Knife129 >{:.1f}%".format(pct_vs_129))
        else:
            khuyen_nghi = "⏸️ GIỮ"
            mo_ta = "Xu hướng tăng, chưa có tín hiệu đặc biệt. Giữ CP, không mua thêm khi chưa có vol."

    elif xu_huong == "SIDEWAY":
        # Kiệt thanh khoản + RSI thấp + vol MA20 đang nhích lên = cơ hội thăm dò
        kiet_thanh_khoan = v_ratio < 0.6
        rsi_qua_ban = pd.notna(rsi) and rsi <= 32
        vol_nhich_len = vol_ma20_trend > 0
        gia_duoi_129 = pct_vs_129 <= 0

        if kiet_thanh_khoan and rsi_qua_ban and vol_nhich_len and gia_duoi_129:
            khuyen_nghi = "🔵 MUA THĂM DÒ (10%)"
            mo_ta = "Sideway vùng đáy: thanh khoản kiệt, RSI thấp, vol MA20 đang nhích lên — dấu hiệu cạn cung."
            ly_do.append(f"📊 Vol chỉ {v_ratio:.2f}x MA20 → kiệt thanh khoản")
            ly_do.append(f"📉 RSI = {rsi:.1f} → vùng quá bán")
            ly_do.append(f"📈 Vol MA20 đang nhích lên (+{vol_ma20_trend:,.0f} cp) → tích lũy")
            ly_do.append(f"💰 Giá dưới Knife129 {abs(pct_vs_129):.1f}% → chiết khấu")
        elif rsi_qua_ban and gia_duoi_129:
            khuyen_nghi = "🔵 MUA THĂM DÒ (5%)"
            mo_ta = "Sideway quá bán, giá dưới Knife129. Chưa có xác nhận vol — chỉ thăm dò nhỏ."
            ly_do.append(f"📉 RSI = {rsi:.1f} → quá bán")
        elif pd.notna(rsi) and rsi >= 68:
            khuyen_nghi = "🔴 BÁN MỘT PHẦN"
            mo_ta = "Sideway nhưng RSI tiệm cận vùng quá mua. Chốt một phần nếu đang có lợi nhuận."
            ly_do.append(f"📈 RSI = {rsi:.1f} → tiệm cận quá mua")
        else:
            khuyen_nghi = "⏸️ CHỜ"
            mo_ta = "Sideway không rõ tín hiệu. Chờ xác nhận xu hướng từ Knife65/Knife129."

    else:  # GIAM
        if close < latest['knife129'] and v_ratio >= 2.5 and pct_vs_129 <= -10:
            khuyen_nghi = "🟡 BẮT ĐÁY CẨN THẬN (5%)"
            mo_ta = "Giảm sâu, vol đột biến — có thể là cạn hàng cung, thăm dò rất nhỏ."
            ly_do.append(f"⚠️ Xu hướng vẫn GIẢM — chỉ thăm dò nhỏ 5%")
        else:
            khuyen_nghi = "🔴 BÁN / TRÁNH"
            mo_ta = "Xu hướng giảm rõ ràng. Không nên giữ hoặc mua mới."

    # Bổ sung cảnh báo tạo đỉnh
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
        "close": latest['close'],
        "ticker": ticker,
    }


def render_recommendation_tab(get_stock_data_fn, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """
    Render tab Khuyến Nghị MUA/BÁN.
    Gọi từ main.py: render_recommendation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift)
    """
    st.subheader("🎯 Khuyến Nghị MUA / BÁN — Hệ Thống Cô Tiên")
    st.caption("Phân tích dựa trên Kijun17 / Knife65 / Knife129 + Volume MA20 + RSI14 (Sideway)")

    col_input, col_btn = st.columns([3, 1])
    with col_input:
        rec_ticker = st.text_input(
            "Nhập mã cổ phiếu:",
            value="PVT",
            key="rec_ticker_input",
            placeholder="VD: HPG, FPT, PVT..."
        ).upper().strip()
    with col_btn:
        st.write("")
        st.write("")
        run_btn = st.button("🔍 PHÂN TÍCH", type="primary", use_container_width=True)

    if not rec_ticker:
        st.info("Nhập mã cổ phiếu và bấm PHÂN TÍCH.")
        return

    if not run_btn and f"rec_data_{rec_ticker}" not in st.session_state:
        st.info(f"Bấm **PHÂN TÍCH** để xem khuyến nghị cho **{rec_ticker}**.")
        return

    # Load dữ liệu (cache session)
    if run_btn or f"rec_data_{rec_ticker}" not in st.session_state:
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
    xu_huong_label = {"TANG": "🟢 Xu hướng TĂNG", "GIAM": "🔴 Xu hướng GIẢM", "SIDEWAY": "🟡 SIDEWAY"}.get(result["xu_huong"], "—")

    # --- PANEL KHUYẾN NGHỊ ---
    st.divider()

    # Màu background theo khuyến nghị
    color_map = {
        "MUA MẠNH": "#00C853",
        "MUA": "#00E676",
        "MUA THĂM DÒ": "#29B6F6",
        "BẮT ĐÁY": "#FFA726",
        "GIỮ": "#78909C",
        "CHỜ": "#78909C",
        "BÁN MỘT PHẦN": "#FF7043",
        "BÁN": "#FF1744",
        "TRÁNH": "#FF1744",
    }
    kn_color = "#78909C"
    for k, v in color_map.items():
        if k in khuyen_nghi.upper():
            kn_color = v
            break

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {kn_color}22, {kn_color}11);
        border: 2px solid {kn_color};
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 16px;
    ">
        <div style="font-size: 2rem; font-weight: 800; color: {kn_color};">{khuyen_nghi}</div>
        <div style="font-size: 1rem; color: #dcd6ec; margin-top: 6px;">{mo_ta}</div>
    </div>
    """, unsafe_allow_html=True)

    # --- SỐ LIỆU NHANH ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Ngày dữ liệu", str(df.iloc[-1].get('time', df.index[-1]))[:10] if 'time' in df.columns else str(df.index[-1])[:10])
    col2.metric("💰 Giá đóng cửa", f"{close:,.2f}")
    col3.metric("📊 Xu hướng", xu_huong_label)
    col4.metric("📏 Cách Knife129", f"{pct_vs_129:+.2f}%")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("📦 Vol / MA20", f"{v_ratio:.2f}x", help="< 0.6x = kiệt | 1-1.5x = bình thường | > 1.5x = đột biến")
    col6.metric("📈 RSI14", f"{rsi:.1f}" if pd.notna(rsi) else "—")
    col7.metric("📈 Vol MA20 (trend)", "⬆️ Nhích lên" if vol_ma20_trend > 0 else "⬇️ Giảm dần")
    col8.metric("🏹 Knife129", f"{latest['knife129']:,.2f}")

    # --- LÝ DO CHI TIẾT ---
    if ly_do:
        st.markdown("**📋 Các tín hiệu chính:**")
        for ld in ly_do:
            st.markdown(f"- {ld}")

    # --- BẢNG 3 ĐƯỜNG ---
    st.divider()
    st.markdown("**📐 3 Đường Định Giá Cô Tiên:**")
    d3_col1, d3_col2, d3_col3 = st.columns(3)
    d3_col1.metric("Kijun17 (nhanh)", f"{latest['kijun17']:,.2f}",
                   "⬆️ Đang lên" if latest['kijun17_up'] else "⬇️ Đang xuống")
    d3_col2.metric("Knife65 (trung)", f"{latest['knife65']:,.2f}",
                   "⬆️ Đang lên" if latest['knife65_up'] else "⬇️ Đang xuống")
    d3_col3.metric("Knife129 (quan trọng nhất)", f"{latest['knife129']:,.2f}",
                   "⬆️ Đang lên" if latest['knife129_up'] else "⬇️ Đang xuống")

    # --- BIỂU ĐỒ ---
    st.divider()
    st.markdown(f"**📊 Biểu Đồ Phân Tích: {ticker} (100 phiên gần nhất)**")

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

    # Nến giá
    candle_colors = ['#00C853' if row['close'] >= row['open'] else '#FF1744' for _, row in plot_df.iterrows()]
    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df['open'], high=plot_df['high'],
        low=plot_df['low'], close=plot_df['close'],
        increasing_line_color='#00C853', decreasing_line_color='#FF1744',
        name='Giá', showlegend=False
    ), row=1, col=1)

    # Mây Ichimoku cổ điển (mờ)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['senkou_a'],
        line=dict(color='rgba(0,200,83,0.3)', width=1), name='Senkou A', showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['senkou_b'],
        line=dict(color='rgba(255,23,68,0.3)', width=1),
        fill='tonexty', fillcolor='rgba(128,128,128,0.1)', name='Mây Kumo', showlegend=True
    ), row=1, col=1)

    # 3 đường Cô Tiên
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['kijun17'],
        line=dict(color='#29B6F6', width=1.5, dash='dot'), name='Kijun17'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['knife65'],
        line=dict(color='#FFA726', width=2), name='Knife65'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['knife129'],
        line=dict(color='#EF5350', width=2.5), name='Knife129 ★'
    ), row=1, col=1)

    # Volume + MA20
    vol_colors = ['#00C853' if plot_df['close'].iloc[i] >= plot_df['open'].iloc[i] else '#FF1744'
                  for i in range(len(plot_df))]
    fig.add_trace(go.Bar(
        x=plot_df.index, y=plot_df['volume'],
        marker_color=vol_colors, name='Volume', showlegend=False
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['vol_ma20'],
        line=dict(color='#FF6D00', width=2, shape='spline'), name='Vol MA20'
    ), row=2, col=1)

    # RSI14 + vùng quá mua/quá bán
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df['rsi14'],
        line=dict(color='#CE93D8', width=1.5), name='RSI14'
    ), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,68,68,0.5)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,200,83,0.5)", row=3, col=1)
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(200,200,200,0.05)", row=3, col=1)

    fig.update_layout(
        height=750,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#dcd6ec'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
        dragmode='pan',
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

    st.plotly_chart(fig, use_container_width=True)

    # --- HƯỚNG DẪN ĐỌC ---
    with st.expander("📖 Hướng dẫn đọc khuyến nghị Cô Tiên"):
        st.markdown("""
**Cách hệ thống ra quyết định:**

| Tín hiệu | Ý nghĩa |
|---|---|
| 🟢 **MUA MẠNH** | Xu hướng TĂNG + Giá chiết khấu sát Knife129 + Vol đột biến ≥ 2x MA20 |
| 🟢 **MUA** | Xu hướng TĂNG + Giá hợp lý (≤15% trên Knife129) + Vol ≥ 1.2x MA20 |
| 🔵 **MUA THĂM DÒ (10%)** | Sideway + Kiệt thanh khoản (Vol < 0.6x) + RSI ≤ 32 + Vol MA20 đang nhích lên + Giá dưới Knife129 |
| 🔵 **MUA THĂM DÒ (5%)** | Sideway + RSI ≤ 32 + Giá dưới Knife129 (chưa có xác nhận vol) |
| ⏸️ **GIỮ** | Xu hướng TĂNG nhưng chưa có tín hiệu vol, hoặc giá đã đi xa |
| ⏸️ **CHỜ** | Sideway không rõ tín hiệu, chờ Knife65/129 xác nhận |
| 🔴 **BÁN MỘT PHẦN** | RSI tiệm cận quá mua trong Sideway, hoặc cảnh báo tạo đỉnh |
| 🔴 **BÁN / TRÁNH** | Xu hướng GIẢM rõ ràng (cả 3 đường quay đầu xuống) |

**Knife129 là đường quan trọng nhất:**
- Giá dưới Knife129 → vùng chiết khấu, xem xét mua
- Giá vượt Knife129 + 15% → cảnh báo mua đuổi
- Giá cắt xuống Knife129 → tín hiệu kết thúc xu hướng tăng

**RSI14 chỉ dùng khi SIDEWAY** — đúng theo triết lý Cô Tiên.
        """)
