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
            p_tenkan = st.number_input("Tenkan-sen", value=9, step=1)
            p_kijun = st.number_input("Kijun-sen", value=26, step=1)
            p_senkou_b = st.number_input("Senkou B", value=52, step=1)
            p_shift = st.number_input("Shift", value=26, step=1)
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift


def render_market_tab(chart_df, df_today):
    st.subheader("Nhịp Đập Thị Trường")
    if chart_df is not None and not chart_df.empty:
        st.line_chart(chart_df, color=["#FF0000", "#00FF00"], height=380)

def render_screener_results(results_df, signal_filter):
    # Đảm bảo dữ liệu luôn là Bảng Pandas
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    
    if not results_df.empty:
        # Lọc trạng thái
        if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        # DỌN DẸP RÁC: Xóa ngay các cột có tên là số (nếu có do lỗi cũ sinh ra)
        cols_to_drop = [c for c in results_df.columns if str(c).isdigit() or str(c).lower() == 'index']
        results_df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
            
        # XỬ LÝ SỐ THẬP PHÂN: Làm tròn 2 chữ số
        for col in results_df.columns:
            if results_df[col].dtype == 'float64':
                results_df[col] = results_df[col].round(2)
                
        # 👑 CHIÊU CUỐI: Ép thẳng 'Mã CK' làm Chỉ mục (Index) thay cho cột số
        if 'Mã CK' in results_df.columns:
            results_df.set_index('Mã CK', inplace=True)
        
        # IN BẢNG RA: Lúc này Mã CK đã chiếm vị trí Index, cột số 9 sẽ biến mất vĩnh viễn!
        st.dataframe(results_df, use_container_width=True)
    else:
        st.info("Chưa có dữ liệu hoặc không có mã nào thỏa mãn điều kiện lọc.")
