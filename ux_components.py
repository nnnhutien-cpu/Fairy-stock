import streamlit as st
import pandas as pd


def setup_cache_clear_button():
    if st.sidebar.button("🧹 XÓA BỘ NHỚ CACHE", use_container_width=True):
        st.cache_data.clear()
        st.sidebar.success("Đã làm sạch toàn bộ hệ thống!")


@st.cache_data(show_spinner=False)
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')


def render_search_and_export(results_df):
    # 1. Bảo vệ lỗi: rỗng hoặc không phải DataFrame
    if results_df is None:
        return results_df
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    if results_df.empty:
        return results_df

    # 2. UI thanh tìm kiếm + nút tải CSV
    col1, col2 = st.columns([3, 1])
    with col1:
        search_query = st.text_input("🔍 Nhập mã cổ phiếu cần tìm (VD: SSI, HPG):", "").upper().strip()
    with col2:
        csv_data = convert_df_to_csv(results_df)
        st.download_button(
            label="📥 Tải file (CSV)",
            data=csv_data,
            file_name="Danh_Sach_Sieu_Co_Phieu.csv",
            mime="text/csv",
            use_container_width=True
        )

    # 3. Lọc theo mã (ép sang chuỗi để không lỗi nếu cột không phải string)
    if search_query and 'Mã CP' in results_df.columns:
        results_df = results_df[
            results_df['Mã CP'].astype(str).str.contains(search_query, case=False, na=False)
        ]

    # CHỈ TRẢ VỀ DỮ LIỆU — không dùng st.dataframe() ở đây
    return results_df
