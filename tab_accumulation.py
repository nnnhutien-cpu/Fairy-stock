# -*- coding: utf-8 -*-
"""
tab_accumulation.py
====================
Tab "🧭 Tích Lũy" cho app Fairy-stock (Cô Tiên Stock).

Cài đặt phương pháp giao dịch theo pha tích lũy:
- RSI(14): vùng quá bán (<30) => vùng giá hời để giải ngân;
  vùng quá mua (>70) => canh hạ tỷ trọng.
- Ichimoku (Tenkan/Kijun/Senkou A-B) + MA129: xác định giá đang TRÊN/DƯỚI mây
  và trên/dưới trục tăng trưởng MA129 để biết uptrend còn hiệu lực hay đã kết thúc.
- Dòng tiền (Volume):
    + "Phiên kiệt thanh khoản" = volume rơi về vùng thấp nhất trong N phiên gần nhất
      (thường đi kèm nến rũ ở vùng giá thấp) => cơ hội giải ngân.
    + "Phiên bùng nổ" = volume vọt lên vượt xa MA20 volume => xác nhận dòng tiền lớn
      nhập cuộc, ủng hộ xu hướng tăng.
- Phân loại trạng thái thị trường/cổ phiếu:
    UPTREND       : giá trên mây + trên MA129 + có dòng tiền bùng nổ hỗ trợ.
    TÍCH LŨY      : giá đã chui xuống dưới mây / thủng MA129 NHƯNG vẫn xuất hiện
                    các phiên khối lượng lớn mua vào ở vùng giá thấp (không hề
                    "vắng bóng dòng tiền lớn") => đi ngang tìm cân bằng, KHÔNG phải downtrend.
    DOWNTREND THẬT: giá dưới mây / dưới MA129 kéo dài MÀ hoàn toàn vắng bóng
                    các phiên volume bùng nổ ở vùng giá thấp => dòng tiền lớn
                    đã rút hẳn, rủi ro giảm sâu tiếp diễn.

Cách tích hợp vào main.py hiện có của bạn:
------------------------------------------
1) Copy file này vào cùng thư mục với main.py (repo Fairy-stock).
2) Trong main.py, thêm import:

    from tab_accumulation import render_accumulation_tab

3) Sửa dòng tạo tabs (hiện đang có 5 tab) thành 6 tab, ví dụ:

    tab_market, tab_screener, tab_simulation, tab_backtest, tab_reports, tab_accum = st.tabs([
        "🌟 Thị Trường", "🔍 Bộ Lọc", "🔮 Mô Phỏng", "🛠️ Backtest", "📑 Báo Cáo", "🧭 Tích Lũy"
    ])

4) Thêm khối gọi hàm ở cuối file (ngang hàng với các "with tab_xxx:" khác):

    with tab_accum:
        render_accumulation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift)

   (get_stock_data đã được import sẵn ở đầu main.py từ data_loader,
    p_tenkan/p_kijun/p_senkou_b/p_shift đã lấy từ render_sidebar() ở phần đầu main.py)
"""

import streamlit as st
import pandas as pd
import numpy as np


# ----------------------------------------------------------------------------
# 1. CÁC HÀM TÍNH TOÁN CHỈ BÁO
# ----------------------------------------------------------------------------

def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI kiểu Wilder (chuẩn, dùng EMA cho trung bình tăng/giảm)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)  # giai đoạn chưa đủ dữ liệu / không có biến động -> trung tính
    return rsi


def calculate_full_indicators(df: pd.DataFrame, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26,
                               ma_trend_period=129, vol_ma_period=20,
                               climax_window=20, breakout_multiplier=1.8) -> pd.DataFrame:
    """Tính RSI, Ichimoku, MA129 và các cờ về dòng tiền (bùng nổ / kiệt thanh khoản)."""
    d = df.copy()
    d.columns = [str(c).lower().strip() for c in d.columns]

    # --- RSI ---
    d['RSI'] = calculate_rsi(d['close'], 14)

    # --- Ichimoku ---
    d['Tenkan'] = (d['high'].rolling(p_tenkan).max() + d['low'].rolling(p_tenkan).min()) / 2
    d['Kijun'] = (d['high'].rolling(p_kijun).max() + d['low'].rolling(p_kijun).min()) / 2
    senkou_a_raw = (d['Tenkan'] + d['Kijun']) / 2
    senkou_b_raw = (d['high'].rolling(p_senkou_b).max() + d['low'].rolling(p_senkou_b).min()) / 2
    d['Senkou_A'] = senkou_a_raw.shift(p_shift)
    d['Senkou_B'] = senkou_b_raw.shift(p_shift)
    d['Cloud_Top'] = d[['Senkou_A', 'Senkou_B']].max(axis=1)
    d['Cloud_Bot'] = d[['Senkou_A', 'Senkou_B']].min(axis=1)

    # --- Trục tăng trưởng MA129 ---
    d[f'MA{ma_trend_period}'] = d['close'].rolling(ma_trend_period).mean()

    # --- Dòng tiền ---
    d['Vol_MA20'] = d['volume'].rolling(vol_ma_period).mean()
    d['Vol_Ratio'] = d['volume'] / d['Vol_MA20'].replace(0, np.nan)

    # Phiên bùng nổ: khối lượng vượt xa trung bình 20 phiên
    d['Bung_No'] = d['Vol_Ratio'] >= breakout_multiplier

    # Phiên kiệt thanh khoản: volume thấp nhất (hoặc gần nhất) trong N phiên gần đây
    d['Rolling_Min_Vol'] = d['volume'].rolling(climax_window).min()
    d['Kiet_Thanh_Khoan'] = d['volume'] <= (d['Rolling_Min_Vol'] * 1.05)

    # --- Vị trí giá so với mây & MA129 ---
    d['Tren_May'] = d['close'] > d['Cloud_Top']
    d['Duoi_May'] = d['close'] < d['Cloud_Bot']
    d['Trong_May'] = (~d['Tren_May']) & (~d['Duoi_May'])
    d['Tren_MA129'] = d['close'] > d[f'MA{ma_trend_period}']

    return d


def classify_state(d: pd.DataFrame, lookback: int = 40, breakout_multiplier: float = 1.8) -> dict:
    """
    Phân loại trạng thái hiện tại theo đúng phương pháp luận:
      - UPTREND: trên mây + trên MA129 + có dòng tiền bùng nổ gần đây.
      - DOWNTREND THẬT: dưới mây/MA129 kéo dài + hoàn toàn vắng bóng phiên bùng nổ.
      - TÍCH LŨY (SIDEWAY): đã rời uptrend (thủng mây/MA129) nhưng vẫn có phiên
        khối lượng lớn xuất hiện ở vùng giá thấp -> chỉ là rũ hàng/tích lũy, chưa phải downtrend.
    """
    last = d.iloc[-1]
    recent = d.tail(lookback)

    tren_may_now = bool(last['Tren_May'])
    tren_ma129_now = bool(last['Tren_MA129'])
    co_bung_no_gan_day = bool(recent['Bung_No'].tail(10).any())
    co_bung_no_trong_lookback = bool(recent['Bung_No'].any())

    if tren_may_now and tren_ma129_now and co_bung_no_gan_day:
        state = "UPTREND"
    elif (not tren_may_now) or (not tren_ma129_now):
        # đã rời khỏi điều kiện uptrend chuẩn -> phân biệt tích lũy vs downtrend thật
        if co_bung_no_trong_lookback:
            state = "TICH_LUY"
        else:
            state = "DOWNTREND"
    else:
        state = "TICH_LUY"

    return {
        "state": state,
        "tren_may": tren_may_now,
        "tren_ma129": tren_ma129_now,
        "co_bung_no_gan_day": co_bung_no_gan_day,
        "co_bung_no_trong_lookback": co_bung_no_trong_lookback,
        "rsi_now": round(float(last['RSI']), 1),
        "kiet_thanh_khoan_now": bool(last['Kiet_Thanh_Khoan']),
        "bung_no_now": bool(last['Bung_No']),
    }


def build_action_signal(info: dict) -> dict:
    """Sinh khuyến nghị hành động theo đúng nguyên tắc 'giao dịch theo pha tích lũy'."""
    rsi = info['rsi_now']
    state = info['state']

    if rsi < 30 or info['kiet_thanh_khoan_now']:
        action = "GIẢI NGÂN (mua tích lũy)"
        color = "#00C853"
        reason = []
        if rsi < 30:
            reason.append(f"RSI đang ở vùng quá bán ({rsi})")
        if info['kiet_thanh_khoan_now']:
            reason.append("phiên hiện tại thuộc nhóm kiệt thanh khoản nhất gần đây")
        reason_txt = " và ".join(reason)
    elif rsi > 70:
        action = "HẠ BỚT TỶ TRỌNG"
        color = "#FF1744"
        reason_txt = f"RSI đang ở vùng quá mua ({rsi})"
    else:
        action = "QUAN SÁT / GIỮ NGUYÊN TỶ TRỌNG"
        color = "#FFAB00"
        reason_txt = f"RSI trung tính ({rsi}), chưa vào vùng cực đoan"

    if state == "TICH_LUY":
        extra = ("Thị trường/cổ phiếu đang trong pha TÍCH LŨY (sideway) — tuyệt đối không mua đuổi "
                 "(breakout) hay dùng margin, ưu tiên giải ngân dần theo vùng giá hời thay vì all-in.")
    elif state == "DOWNTREND":
        extra = ("Cảnh báo: đây có dấu hiệu DOWNTREND THẬT (giá dưới mây/MA129 kéo dài, vắng hẳn "
                 "phiên bùng nổ ở vùng giá thấp) — nên thận trọng, không vội bắt đáy sớm dù RSI quá bán.")
    else:
        extra = "Xu hướng tăng vẫn còn hiệu lực (trên mây, trên MA129, có dòng tiền bùng nổ hỗ trợ)."

    return {"action": action, "color": color, "reason": reason_txt, "extra": extra}


# ----------------------------------------------------------------------------
# 2. RENDER TAB STREAMLIT
# ----------------------------------------------------------------------------

def render_accumulation_tab(get_stock_data_fn, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """Vẽ toàn bộ nội dung tab 'Tích Lũy'. Gọi trong main.py bên trong `with tab_accum:`."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    st.subheader("🧭 Chiến Lược Giao Dịch Theo Pha Tích Lũy")
    st.caption(
        "RSI xác định vùng giá hời/quá mua · Mây Ichimoku + MA129 xác định trạng thái xu hướng · "
        "Volume xác định dòng tiền lớn còn hay đã rút, để phân biệt TÍCH LŨY thật với DOWNTREND thật."
    )

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        ticker = st.text_input(
            "Nhập mã (hoặc VNINDEX):", value="VNINDEX", key="accum_ticker_input"
        ).upper().strip()
    with col_b:
        climax_window = st.number_input("Cửa sổ xét kiệt TK (phiên)", min_value=5, max_value=60, value=20, step=5)
    with col_c:
        breakout_mult = st.number_input("Ngưỡng bùng nổ (x Vol MA20)", min_value=1.2, max_value=4.0, value=1.8, step=0.1)

    if not ticker:
        st.info("Nhập mã cổ phiếu hoặc VNINDEX để bắt đầu phân tích.")
        return

    with st.spinner(f"Đang tải và tính toán dữ liệu {ticker}..."):
        df = get_stock_data_fn(ticker, days_back=400) if ticker != "VNINDEX" else get_stock_data_fn("VNINDEX", days_back=400)

    if df is None or df.empty:
        st.warning(f"⚠️ Không lấy được dữ liệu cho {ticker}. Kiểm tra lại mã hoặc thử lại sau.")
        return

    d = calculate_full_indicators(
        df, p_tenkan=p_tenkan, p_kijun=p_kijun, p_senkou_b=p_senkou_b, p_shift=p_shift,
        climax_window=int(climax_window), breakout_multiplier=float(breakout_mult)
    )
    d = d.dropna(subset=['close']).reset_index(drop=True)

    if len(d) < 130:
        st.warning("⚠️ Dữ liệu chưa đủ dài (cần tối thiểu ~130 phiên) để tính MA129 & mây Ichimoku chuẩn xác.")

    info = classify_state(d, lookback=40, breakout_multiplier=float(breakout_mult))
    signal = build_action_signal(info)

    # --- Bảng chỉ số nhanh ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("RSI(14) hiện tại", info['rsi_now'])
    m2.metric("Vị trí giá / Mây", "TRÊN MÂY ✅" if info['tren_may'] else "DƯỚI/TRONG MÂY ⚠️")
    m3.metric("Vị trí giá / MA129", "TRÊN MA129 ✅" if info['tren_ma129'] else "DƯỚI MA129 ⚠️")
    state_label = {"UPTREND": "🟢 UPTREND", "TICH_LUY": "🟡 TÍCH LŨY (SIDEWAY)", "DOWNTREND": "🔴 DOWNTREND THẬT"}
    m4.metric("Phân loại trạng thái", state_label.get(info['state'], info['state']))

    st.markdown(
        f"""
        <div style="background:#1a1436; border:1px solid {signal['color']}; border-radius:14px;
                    padding:18px 20px; margin-top:10px;">
            <div style="font-size:1.1rem; font-weight:700; color:{signal['color']};">
                ⚡ Khuyến nghị hành động: {signal['action']}
            </div>
            <div style="color:#dcd6ec; margin-top:6px;">Lý do: {signal['reason']}.</div>
            <div style="color:#a99fcf; margin-top:6px; font-size:.9rem;">{signal['extra']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # --- Biểu đồ: Giá + Mây + MA129 (row1), Volume + cờ bùng nổ/kiệt TK (row2), RSI (row3) ---
    plot_df = d.tail(180).copy()
    if 'time' in plot_df.columns:
        plot_df['Ngay'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
        plot_df.set_index('Ngay', inplace=True)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.55, 0.2, 0.25]
    )

    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['close'], line=dict(color='#c4b5fd', width=2), name='Giá'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Senkou_A'], line=dict(color='rgba(0,200,83,0.4)', width=1), name='Senkou A'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Senkou_B'], line=dict(color='rgba(255,23,68,0.4)', width=1),
                              fill='tonexty', fillcolor='rgba(128,128,128,0.15)', name='Mây Kumo'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA129'], line=dict(color='#FF6D00', width=2), name='MA129'), row=1, col=1)

    colors_vol = ['#00C853' if b else ('#2962FF' if k else '#5a5379')
                  for b, k in zip(plot_df['Bung_No'], plot_df['Kiet_Thanh_Khoan'])]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['volume'], marker_color=colors_vol, name='Volume'), row=2, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Vol_MA20'], line=dict(color='#FFAB00', width=1.5), name='Vol MA20'), row=2, col=1)

    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], line=dict(color='#a394d4', width=2), name='RSI(14)'), row=3, col=1)
    fig.add_hline(y=70, line=dict(color='#FF1744', width=1, dash='dash'), row=3, col=1)
    fig.add_hline(y=30, line=dict(color='#00C853', width=1, dash='dash'), row=3, col=1)

    fig.update_layout(
        title=f"<b>{ticker}: Ichimoku + MA129 + RSI + Dòng Tiền</b>",
        height=780, margin=dict(l=10, r=10, t=40, b=10),
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False, dragmode='pan',
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#dcd6ec')
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(range=[0, 100], row=3, col=1)

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "🟢 Cột volume xanh lá = phiên bùng nổ (dòng tiền lớn) · 🔵 xanh dương = phiên kiệt thanh khoản · "
        "⚪ xám = phiên bình thường. Đường cam MA129 là trục tăng trưởng; giá thủng MA129 + mây "
        "nhưng vẫn có cột xanh lá xuất hiện ở vùng giá thấp = tích lũy, KHÔNG phải downtrend."
    )
