mport streamlit as st

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

        

        # CHỌN CỘT THỦ CÔNG: Chỉ cho phép các cột này hiện ra, các cột khác (như cột 9) sẽ bị loại bỏ

        allowed_cols = ['Mã CK', 'Trạng thái', 'RSI', 'MACD', 'Tín hiệu'] # Thêm các tên cột thực tế của bạn vào đây

        # Nếu không biết tên cột chính xác, hãy lấy tất cả trừ các cột là số:

        cols_to_use = [c for c in results_df.columns if not str(c).isdigit()]

        results_df = results_df[cols_to_use]

            

        # Nhấc Mã CK lên đầu

        if 'Mã CK' in results_df.columns:

            cols = ['Mã CK'] + [c for c in results_df.columns if c != 'Mã CK']

            results_df = results_df[cols]

                

        st.dataframe(results_df, use_container_width=True, hide_index=True)

    else:

        st.info("Chưa có dữ liệu.") 

