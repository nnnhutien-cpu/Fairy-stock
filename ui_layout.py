import streamlit as st
import pandas as pd

def render_sidebar():
    """Vẽ thanh điều khiển cấu hình bộ lọc bên trái"""
    with st.sidebar:
        st.title("🧚‍♀️ CÔ TIÊN STOCK")
        st.caption("Hệ thống phân tích thông minh")
        st.divider()
        
        st.header("⚙️ CẤU HÌNH BỘ LỌC")
        exchange_choice = st.selectbox("Chọn sàn giao dịch:", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
        signal_filter = st.radio("Bộ lọc tín hiệu kỹ thuật:", ["Tất cả", "🟢 Tích cực", "🔴 Tiêu cực"])
        max_scan = st.slider("Số lượng mã quét tối đa:", 10, 300, 80)
        
    return exchange_choice, signal_filter, max_scan

def render_market_tab(chart_df, df_today):
    """Vẽ Tab 1: Biểu đồ so sánh thanh khoản hôm nay và hôm qua"""
    st.subheader("Nhịp Đập Thị Trường (Thanh khoản Real-time)")
    
    if chart_df is not None and df_today is not None and not df_today.empty:
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            latest_point = df_today.iloc[-1]
            
            # [BỌC THÉP] Dùng .get() để chống sập web. Không có dữ liệu thì hiện N/A hoặc số 0
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
                    st.metric(label="% Thanh Khoản (So với cùng giờ hôm qua)", 
                              value=f"{vol_diff_pct:+.2f}%", 
                              delta=f"{vol_diff_pct:+.2f}%", delta_color="normal")
                else:
                    st.metric(label="% Thanh Khoản", value="Đang tính toán...")
        
        st.markdown("**📈 Biểu Đồ Thanh Khoản Cộng Dồn Trong Phiên (Đỏ: Hôm qua | Xanh: Hôm nay)**")
        st.line_chart(chart_df, color=["#FF0000", "#00FF00"], height=380)
    else:
        st.warning("Đang kết nối dữ liệu Real-time hoặc thị trường đang trong trạng thái đóng cửa phiên...")

def render_screener_results(results, signal_filter):
    """Lọc dữ liệu theo lựa chọn Tích cực / Tiêu cực và xuất bảng"""
    if results:
        results_df = pd.DataFrame(results)
        
        if signal_filter != "Tất cả":
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        if not results_df.empty:
            st.dataframe(
                results_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Volume Hiện Tại": st.column_config.NumberColumn(format="%d"),
                    "Volume TB 20 Phiên": st.column_config.NumberColumn(format="%d"),
                    "Giá": st.column_config.NumberColumn(format="%.2f"),
                    "GTGD (Tỷ)": st.column_config.NumberColumn(format="%.2f")
                }
            )
            st.toast("Đã hiển thị danh sách siêu lọc dòng tiền thành công!", icon="🧚‍♀️")
        else:
            st.info(f"Không có mã nào thuộc nhóm trạng thái '{signal_filter}' đạt điều kiện thanh khoản > 20 Tỷ.")
    else:
        st.info("Không tìm thấy mã nào đạt điều kiện thanh khoản cơ sở giao dịch trên 20 Tỷ.")
