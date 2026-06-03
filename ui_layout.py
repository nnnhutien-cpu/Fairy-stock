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
                st.metric(label=f"VN-INDEX ({current_time})", value=f"{close_price:.2f}")
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

def render_screener_results(results, signal_filter):
    if results:
        results_df = pd.DataFrame(results)
        if signal_filter != "Tất cả":
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        if not results_df.empty:
            st.dataframe(
                results_df, use_container_width=True, hide_index=True,
                column_config={
                    "Khối Lượng": st.column_config.NumberColumn(format="%d"),
                    "KL TB 20 Phiên": st.column_config.NumberColumn(format="%d"),
                    "Giá": st.column_config.NumberColumn(format="%.2f"),
                    "GTGD (Tỷ)": st.column_config.NumberColumn(format="%.2f"),
                    "Tenkan": st.column_config.NumberColumn(format="%.2
