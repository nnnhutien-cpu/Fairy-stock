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
    """Render biểu đồ Nhịp Đập Thị Trường (tick-by-tick realtime).

    Lưu ý: phần Định giá P/E 20 năm đã được chuyển sang card riêng
    trong main.py (mục "📊 Phân tích Xu hướng") để tránh hiển thị 2 lần.
    """

    # ── Biểu đồ dòng tiền (Nhịp Đập Thị Trường) ─────────────────────────
    st.subheader("💓 Nhịp Đập Thị Trường (Realtime tick-by-tick)")
    if chart_df is not None and not chart_df.empty:
        st.line_chart(chart_df, color=["#8b7fb5", "#34d399"], height=380)
        st.caption("🟣 Hôm qua (tham chiếu) · 🟢 Hôm nay (real-time)")
    else:
        st.info("📡 Chưa có dữ liệu biểu đồ. Dữ liệu VN-INDEX đang được tải hoặc thị trường chưa mở phiên.")


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
