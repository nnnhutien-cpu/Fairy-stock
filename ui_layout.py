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
            help="Ưu tiên quét các mã lớn, gần như chắc chắn đủ thanh khoản để lọt bộ lọc -> có kết quả nhanh trong 1-3 phút. "
                 "Tắt đi nếu muốn quét toàn sàn (chậm hơn nhiều vì phải quét cả mã nhỏ, ít thanh khoản)."
        )
        vnstock_api_key = st.text_input(
            "🔑 API Key vnstock (không bắt buộc):", value="", type="password",
            help="Dán API key miễn phí lấy từ vnstocks.com/login để tăng tốc độ quét từ 20 lên 60 mã/phút."
        )

        with st.expander("🛠️ TÙY CHỈNH ICHIMOKU (NÂNG CAO)", expanded=False):
            p_tenkan = st.number_input("Tenkan-sen", value=9, step=1)
            p_kijun = st.number_input("Kijun-sen", value=26, step=1)
            p_senkou_b = st.number_input("Senkou B", value=52, step=1)
            p_shift = st.number_input("Shift", value=26, step=1)
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, vnstock_api_key, fast_mode


def render_market_tab(chart_df, df_today):
    st.subheader("Nhịp Đập Thị Trường")
    if chart_df is not None and not chart_df.empty:
        # màu khớp theme tím: hôm qua = tím mờ (tham chiếu), hôm nay = xanh nổi
        st.line_chart(chart_df, color=["#8b7fb5", "#34d399"], height=380)
        st.caption("🟣 Hôm qua (tham chiếu) · 🟢 Hôm nay (real-time)")
    else:
        st.info("📡 Chưa có dữ liệu biểu đồ. Dữ liệu VN-INDEX đang được tải hoặc thị trường chưa mở phiên.")


def render_screener_results(results_df, signal_filter):
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)

    if not results_df.empty:
        if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
            results_df = results_df[results_df['Trạng thái'] == signal_filter]

        # Loại cột rác tên "9" nếu có
        cols_to_use = [col for col in results_df.columns if str(col) != '9']
        df_display = results_df[cols_to_use]

        st.caption(f"📊 Tìm thấy {len(df_display)} mã khớp bộ lọc.")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có dữ liệu.")
