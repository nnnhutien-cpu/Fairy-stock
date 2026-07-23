import streamlit as st
import pandas as pd


def render_sidebar():
    with st.sidebar:
        st.title("🧚‍♀️ CÔ TIÊN STOCK")
        st.caption("Hệ thống phân tích thông minh")
        st.divider()
        st.header("⚙️ CẤU HÌNH BỘ LỌC")
        exchange_choice = st.selectbox("Chọn sàn giao dịch:", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
        signal_filter = st.radio("Bộ lọc tín hiệu kỹ thuật:", ["Tất cả", "🟢 Tích cực", "🔴 Tiêu cực"])
        max_scan = st.slider("Số lượng mã quét tối đa:", 10, 2000, 100)
        st.caption(
            "⏱️ vnstock giới hạn **20 request/phút** cho tài khoản khách (chưa có API key). "
            "Quét 100 mã mất khoảng 5 phút. Đăng ký API key MIỄN PHÍ tại "
            "[vnstocks.com/login](https://vnstocks.com/login) để tăng lên **60 request/phút** (nhanh gấp 3)."
        )
        fast_mode = st.checkbox(
            "⚡ Chế độ NHANH: chỉ quét nhóm vốn hoá lớn/thanh khoản cao (~60 mã)",
            value=True,
            help="Ưu tiên quét các mã lớn, gần như chắc chắn đủ thanh khoản -> có kết quả nhanh trong 1-3 phút."
        )
        vnstock_api_key = st.text_input(
            "🔑 API Key vnstock (không bắt buộc):", value="", type="password",
            help="Dán API key miễn phí lấy từ vnstocks.com/login để tăng tốc độ quét từ 20 lên 60 mã/phút."
        )
        with st.expander("🛠️ TÙY CHỈNH ICHIMOKU (NÂNG CAO)", expanded=False):
            p_tenkan   = st.number_input("Tenkan-sen", value=9,  step=1)
            p_kijun    = st.number_input("Kijun-sen",  value=26, step=1)
            p_senkou_b = st.number_input("Senkou B",   value=52, step=1)
            p_shift    = st.number_input("Shift",      value=26, step=1)
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, vnstock_api_key, fast_mode


def render_market_tab(chart_df, df_today):
    """Render toàn bộ Tab Thị Trường: biểu đồ volume + Định giá P/E 20 năm."""

    # ── Biểu đồ dòng tiền ──────────────────────────────────────────────
    st.subheader("Nhịp Đập Thị Trường")
    if chart_df is not None and not chart_df.empty:
        st.line_chart(chart_df, color=["#8b7fb5", "#34d399"], height=380)
        st.caption("🟣 Hôm qua (tham chiếu) · 🟢 Hôm nay (real-time)")
    else:
        st.info("📡 Chưa có dữ liệu biểu đồ. Dữ liệu VN-INDEX đang được tải hoặc thị trường chưa mở phiên.")

    # ── Định giá P/E ──────────────────────────────────────────────────
    st.divider()
    st.subheader("💰 Định giá P/E (20 năm)")

    import valuation

    # Lấy giá VNINDEX mới nhất từ df_today (intraday đang chạy được)
    vnindex_price = None
    if df_today is not None and not df_today.empty and 'close' in df_today.columns:
        try:
            vnindex_price = float(df_today['close'].iloc[-1])
        except Exception:
            vnindex_price = None

    with st.spinner("Đang tính P/E..."):
        pe_now  = valuation.get_current_pe(vnindex_price)
        pe_hist = valuation.get_pe_history(years=20)
        stats   = valuation.pe_stats(pe_hist, pe_now)

    if pe_now is None:
        st.warning("⏳ Chưa có giá VN-INDEX hôm nay. Vui lòng chờ thị trường mở phiên hoặc bấm 🔄 Cập nhật.")
    else:
        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("P/E Hiện tại",  f"{stats['pe_now']:.1f}x")
        c2.metric("TB 20 năm",     f"{stats['mean']:.1f}x"       if stats['mean']              else "—")
        c3.metric("Percentile",    f"{stats['percentile']:.0f}%"  if stats['percentile'] is not None else "—")
        c4.metric("Z-score",       f"{stats['zscore']:+.2f}"      if stats['zscore']  is not None else "—")

        st.markdown(stats["comment"])

        # Biểu đồ lịch sử
        if pe_hist is not None and not pe_hist.empty:
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pe_hist["date"], y=pe_hist["pe"],
                name="P/E VN-INDEX",
                line=dict(color="#c4b5fd", width=2),
                fill="tozeroy", fillcolor="rgba(139,127,181,0.08)",
            ))
            if stats["mean"]:
                fig.add_hline(y=stats["mean"], line_dash="dash", line_color="#facc15",
                              annotation_text=f"TB {stats['mean']:.1f}x",
                              annotation_position="top right")
            if stats["mean"] and stats["stdev"]:
                fig.add_hline(y=stats["mean"] + stats["stdev"], line_dash="dot",
                              line_color="rgba(250,100,100,0.6)",
                              annotation_text=f"+1σ  {stats['mean']+stats['stdev']:.1f}x",
                              annotation_position="top right")
                fig.add_hline(y=stats["mean"] - stats["stdev"], line_dash="dot",
                              line_color="rgba(100,220,100,0.6)",
                              annotation_text=f"-1σ  {stats['mean']-stats['stdev']:.1f}x",
                              annotation_position="bottom right")
            fig.add_hline(y=pe_now, line_color="#f97316", line_width=2,
                          annotation_text=f"Hôm nay {pe_now:.1f}x",
                          annotation_position="top left")

            fig.update_layout(
                height=340,
                margin=dict(l=10, r=10, t=30, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#dcd6ec"),
                showlegend=False,
                yaxis_title="P/E",
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Bảng thống kê chi tiết
        with st.expander("📊 Xem thống kê chi tiết P/E 20 năm"):
            stat_rows = {
                "P/E hiện tại":  f"{stats['pe_now']:.2f}x",
                "Trung bình":    f"{stats['mean']:.2f}x"   if stats['mean']   else "—",
                "Trung vị":      f"{stats['median']:.2f}x" if stats['median'] else "—",
                "Thấp nhất":     f"{stats['min']:.2f}x"    if stats['min']    else "—",
                "Cao nhất":      f"{stats['max']:.2f}x"    if stats['max']    else "—",
                "Độ lệch chuẩn": f"{stats['stdev']:.2f}"   if stats['stdev']  else "—",
                "Percentile":    f"{stats['percentile']:.1f}%" if stats['percentile'] is not None else "—",
                "Z-score":       f"{stats['zscore']:+.2f}"  if stats['zscore'] is not None else "—",
                "% so với TB":   f"{stats['pct_vs_avg']:+.1f}%" if stats['pct_vs_avg'] is not None else "—",
            }
            st.table(pd.DataFrame(stat_rows.items(), columns=["Chỉ số", "Giá trị"]))


def _filter_and_clean(results_df, signal_filter):
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    if results_df.empty:
        return results_df
    if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
        results_df = results_df[results_df['Trạng thái'] == signal_filter]
    cols_to_use = [col for col in results_df.columns if str(col) != '9']
    return results_df[cols_to_use]


def render_screener_results(results_df, signal_filter):
    df = _filter_and_clean(results_df, signal_filter)
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return
    st.caption(f"📊 Tìm thấy {len(df)} mã khớp bộ lọc.")

    def pick(cols):
        return [c for c in cols if c in df.columns]

    groups = {
        "📋 Tổng Quan": pick([
            "Mã CP", "Giá", "GTGD (Tỷ)", "Khối Lượng", "Vol x TB20",
            "Dòng Tiền", "Xu Hướng", "Trạng thái",
        ]),
        "📐 3 Đường Định Giá": pick([
            "Mã CP", "Giá", "Kijun17", "Knife65", "Knife129",
            "Cách Knife129 (%)", "Định Giá (129)", "Hợp Bích (65≈129)",
            "Cảnh Báo Mua Đuổi", "Ichimoku_Cloud",
        ]),
    }
    tabs = st.tabs(list(groups.keys()))
    for tab, label in zip(tabs, groups.keys()):
        with tab:
            cols = groups[label]
            if cols:
                st.dataframe(df[cols], use_container_width=True, hide_index=True)
            else:
                st.caption("Không có cột dữ liệu phù hợp cho nhóm này.")

    with st.expander("🗂️ Xem toàn bộ cột cùng lúc (bảng gốc, đầy đủ)"):
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_screener_signals(results_df, signal_filter):
    df = _filter_and_clean(results_df, signal_filter)
    if df.empty:
        st.info("Chưa có dữ liệu. Sang tab 🔍 Bộ Lọc để quét trước.")
        return
    st.caption(f"📡 {len(df)} mã — tín hiệu RSI/MFI chỉ có ý nghĩa mua/bán khi mã đang ở trạng thái Sideway.")
    cols = [c for c in [
        "Mã CP", "Giá", "Xu Hướng", "Cảnh Báo Tạo Đỉnh",
        "Tín Hiệu Bắt Đáy", "RSI14", "MFI14", "Tín Hiệu Sideway (MFI/RSI)",
    ] if c in df.columns]
    if cols:
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.info("Không có cột tín hiệu phù hợp trong dữ liệu hiện tại.")
