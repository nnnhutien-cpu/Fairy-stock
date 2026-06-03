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
        max_scan = st.slider("Số lượng mã quét tối đa:", 10, 300, 80)
        
        st.divider()
        # BẢNG TÙY CHỈNH THÔNG SỐ ICHIMOKU DÀNH CHO DÂN PRO
        with st.expander("🛠️ TÙY CHỈNH ICHIMOKU (NÂNG CAO)", expanded=False):
            st.caption("Mặc định chuẩn Nhật: 9 - 26 - 52 - 26")
            p_tenkan = st.number_input("Tenkan-sen (Đường chuyển đổi)", value=9, step=1)
            p_kijun = st.number_input("Kijun-sen (Đường cơ sở)", value=26, step=1)
            p_senkou_b = st.number_input("Senkou Span B (Đỉnh/Đáy mây)", value=52, step=1)
            p_shift = st.number_input("Độ dịch chuyển Mây (Shift)", value=26, step=1)
            
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift

def render_market_tab
