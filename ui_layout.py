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
        
        max_scan = st.slider("Số lượng mã quét tối đa:", 10, 2000, 1600)
        
        st.divider()
        with st.expander("🛠️ TÙY CHỈNH ICHIMOKU (NÂNG CAO)", expanded=False):
            st.caption("Mặc định chuẩn Nhật: 9 - 26 - 52 - 26")
            p_tenkan = st.number_input("Tenkan-sen", value=9, step=1)
            p_kijun = st.number_input("Kijun-sen", value=26, step=1)
            p_senkou_b = st.number_input("Senkou B", value=52, step=1)
            p_shift = st.number_input("Shift", value=26, step=1)
            
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift

def render_market_tab(chart_df, df_today):
    st.subheader("Nhịp Đập Thị Trường (Thanh khoản Real-time)")
    if chart_df is not None and df_today is not None and not df_today.empty:
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            latest_point = df_today.iloc[-1]
            current_time = latest_point.get('hour_min', 'N/A')
            close_price = latest_point.get('close', 0.0)
            today_vol_total = latest_point.get('Vol_Hôm_Nay', 0.0)
            
            with col1:
                st.metric(label=f"VN-INDEX ({current_time})", value=f"{close_price:,.2f}")
            with col2:
                st.metric(label="Tổng Khối Lượng Hôm Nay", value=f"{int(today_vol_total):,}")
            with col3:
                yest_vol_same_time = chart_df.loc[current_time, 'Vol_Hôm_Qua'] if current_time in chart_df.index else None
                if pd.notna(yest_vol_same_time) and yest_vol_same_time > 0:
                    vol_diff_pct = ((today_vol_total - yest_vol_same_time) / yest_vol_same_time) * 100
                    st.metric(label="% Thanh Khoản", value=f"{vol_diff_pct:+.2f}%", delta=f"{vol_diff_pct:+.2f}%", delta_color="normal")
                else:
                    st.metric(label="% Thanh Khoản", value="Đang tính toán...")
        st.markdown("**📈 Biểu Đồ Thanh Khoản Cộng Dồn Trong Phiên (Đỏ: Hôm qua | Xanh: Hôm nay)**")
        st.line_chart(chart_df, color=["#FF0000", "#00FF00"], height=380)
    else:
        st.warning("Đang kết nối dữ liệu Real-time hoặc thị trường đang đóng cửa...")

# =========================================================
# [MỚI] CÁC HÀM TỰ ĐỘNG PHỐI MÀU NỀN THEO ĐIỀU KIỆN 
# =========================================================
def color_dong_tien(val):
    """Tô màu nền dịu mắt cho cột Dòng Tiền"""
    if val == "🔥 Tiền Vào Mạnh":
        return "background-color: rgba(0, 200, 83, 0.25); color: #00796B; font-weight: bold;"
    elif val == "💤 Tiền Yếu":
        return "background-color: rgba(255, 23, 68, 0.15); color: #C62828;"
    elif val == "⚡ Có Tín Hiệu":
        return "background-color: rgba(255, 235, 59, 0.3); color: #F57F17;"
    return ""

def color_danh_gia(val):
    """Tô màu nền dịu mắt cho cột Đánh Giá (Mây Ichimoku)"""
    if val == "📉 Định giá Thấp":
        return "background-color: rgba(0, 200, 83, 0.25); color: #00796B; font-weight: bold;"
    elif val == "📈 Định giá Cao":
        return "background-color: rgba(255, 23, 68, 0.15); color: #C62828;"
    elif val == "⚖️ Hợp lý":
        return "background-color: rgba(240, 242, 246, 1); color: #31333F;"
    return ""

def render_screener_results(results, signal_filter):
    if results:
        results_df = pd.DataFrame(results)
        if signal_filter != "Tất cả":
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        if not results_df.empty:
            cols_order = [
                "Mã", "Giá", "GTGD (Tỷ)", "Khối Lượng", "KL TB 20 Phiên", "Đánh Giá", "Dòng Tiền",
                "Tenkan", "Kijun", "Senkou A", "Senkou B", "Chikou", 
                "Ichimoku_Cloud", "Trạng thái"
            ]
            results_df = results_df[[c for c in cols_order if c in results_df.columns]]
            
            # 1. Định dạng cấu hình hiển thị dấu phẩy hàng nghìn và số thập phân
            format_dict = {
                "Giá": "{:,.0f}",
                "Khối Lượng": "{:,.0f}",
                "KL TB 20 Phiên": "{:,.0f}",
                "GTGD (Tỷ)": "{:,.2f}",
                "Tenkan": "{:,.0f}",
                "Kijun": "{:,.0f}",
                "Senkou A": "{:,.0f}",
                "Senkou B": "{:,.0f}",
                "Chikou": "{:,.0f}"
            }
            valid_format_dict = {k: v for k, v in format_dict.items() if k in results_df.columns}
            
            # 2. ÁP DỤNG ĐỊNH DẠNG SỐ VÀ TÔ MÀU BẢNG ĐIỆN ĐỘNG
            styled_df = (results_df.style
                         .format(valid_format_dict)
                         .map(color_dong_tien, subset=['Dòng Tiền'] if 'Dòng Tiền' in results_df.columns else [])
                         .map(color_danh_gia, subset=['Đánh Giá'] if 'Đánh Giá' in results_df.columns else []))
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            st.toast("Đã hiển thị danh sách siêu lọc kỹ thuật thành công!", icon="🧚‍♀️")
        else:
            st.info(f"Không có mã nào thuộc nhóm '{signal_filter}' đạt điều kiện.")
    else:
        st.info("Chưa tìm thấy mã nào đạt điều kiện thanh khoản.")
