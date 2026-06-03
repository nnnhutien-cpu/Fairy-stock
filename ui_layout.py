import streamlit as st
import pandas as pd

def render_sidebar():
    """Vẽ thanh điều khiển bên trái"""
    with st.sidebar:
        st.title("🧚‍♀️ CÔ TIÊN STOCK")
        st.caption("Hệ thống phân tích thông minh")
        st.divider()
        
        st.header("⚙️ CẤU HÌNH BỘ LỌC")
        exchange_choice = st.selectbox("Chọn sàn giao dịch:", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
        max_scan = st.slider("Số lượng mã quét tối đa:", 10, 300, 80)
        
    return exchange_choice, max_scan

def render_market_tab(chart_df, df_today):
    """Vẽ Tab thị trường chung"""
    st.subheader("Nhịp Đập Thị Trường (Khung 5 Phút)")
    
    if chart_df is not None and df_today is not None and not df_today.empty:
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            latest_point = df_today.iloc[-1]
            current_time = latest_point['hour_min']
            
            with col1:
                st.metric(label=f"VN-INDEX ({current_time})", value=f"{latest_point['close']:.2f}")
            with col2:
                today_vol_total = latest_point['Vol_Hôm_Nay']
                st.metric(label="Tổng Khối Lượng Hiện Tại", value=f"{int(today_vol_total):,}")
            with col3:
                yest_vol_same_time = chart_df.loc[current_time, 'Vol_Hôm_Qua'] if current_time in chart_df.index else None
                if pd.notna(yest_vol_same_time) and yest_vol_same_time > 0:
                    vol_diff_pct = ((today_vol_total - yest_vol_same_time) / yest_vol_same_time) * 100
                    st.metric(label="% Thanh Khoản (So với hôm qua)", 
                              value=f"{vol_diff_pct:+.2f}%", 
                              delta=f"{vol_diff_pct:+.2f}%", delta_color="normal")
                else:
                    st.metric(label="% Thanh Khoản (So với hôm qua)", value="Chờ đồng bộ")
        
        st.markdown("**📉 Biểu Đồ So Sánh Thanh Khoản (Đỏ: Hôm qua | Xanh: Hôm nay)**")
        st.line_chart(chart_df, color=["#FF0000", "#00FF00"], height=350)
    else:
        st.warning("Đang kết nối dữ liệu VN-INDEX hoặc ngoài giờ giao dịch...")

def render_screener_results(results):
    """Vẽ bảng kết quả lọc cổ phiếu"""
    if results:
        results_df = pd.DataFrame(results)
        st.dataframe(
            results_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Volume Hiện Tại": st.column_config.NumberColumn(format="%d"),
                "Volume TB 20 Phiên": st.column_config.NumberColumn(format="%d"),
                "Giá": st.column_config.NumberColumn(format="%.2f")
            }
        )
        st.toast("Phân tích hoàn tất! Chúc Cô Tiên giao dịch thành công 🚀", icon="🧚‍♀️")
    else:
        st.info("⚠️ Hiện tại không có mã nào vượt qua được bộ lọc khắt khe (GTGD > 20 Tỷ & Tín hiệu Tích cực) của bạn.")
