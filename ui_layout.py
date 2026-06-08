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
        
        with st.expander("🛠️ TÙY CHỈNH ICHIMOKU (NÂNG CAO)", expanded=False):
            p_tenkan = st.number_input("Tenkan-sen", value=9, step=1, help="Đường Chuyển Đổi")
            p_kijun = st.number_input("Kijun-sen", value=26, step=1, help="Đường Cơ Sở")
            p_senkou_b = st.number_input("Senkou B", value=52, step=1, help="Đường Dẫn Dắt B")
            p_shift = st.number_input("Shift", value=26, step=1, help="Độ dịch chuyển")
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift

def render_market_tab(chart_df, df_today):
    st.subheader("Nhịp Đập Thị Trường")
    if chart_df is not None:
        st.line_chart(chart_df, color=["#FF0000", "#00FF00"], height=380)
        
st.dataframe(df_display, use_container_width=True, hide_index=True)
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    
    if not results_df.empty:
        if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có dữ liệu.")
