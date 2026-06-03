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
            
            p_tenkan = st.number_input("Tenkan-sen", value=9, step=1, help="Đường Chuyển Đổi: Cho thấy tín hiệu đảo chiều ngắn hạn.")
            p_kijun = st.number_input("Kijun-sen", value=26, step=1, help="Đường Cơ Sở: Xác định xu hướng trung hạn và Hỗ trợ/Kháng cự.")
            p_senkou_b = st.number_input("Senkou B", value=52, step=1, help="Đường Dẫn Dắt B: Đường biên dài hạn tạo nên Đám mây Kumo.")
            p_shift = st.number_input("Shift", value=26, step=1, help="Độ dịch chuyển: Đẩy mây Kumo về tương lai & kéo Chikou lùi về quá khứ.")
            
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
                st.metric(label="Tổng Khối Lượng Hôm Nay", value=f"{
