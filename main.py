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
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    
    if not results_df.empty:
        # Lọc trạng thái
        if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        # --- BƯỚC 1: XÓA BIẾN MẤT CỘT 9 ---
        cols = [col for col in results_df.columns if str(col) != '9']
        
        # --- BƯỚC 2: ĐƯA "Mã CK" LÊN ĐẦU TIÊN THAY THẾ ---
        if 'Mã CK' in cols:
            cols.remove('Mã CK')           # Rút cột Mã CK ra khỏi danh sách
            cols = ['Mã CK'] + cols        # Gắn nó lại vào vị trí đầu tiên (Số 1)
        elif 'Mã' in cols:                 # Dự phòng trường hợp cột của bạn tên là 'Mã'
            cols.remove('Mã')
            cols = ['Mã'] + cols

        df_display = results_df[cols]

        # Hiển thị bảng đã được dọn dẹp và sắp xếp lên Streamlit
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có dữ liệu.")
