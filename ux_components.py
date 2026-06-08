import streamlit as st
import pandas as pd

def setup_cache_clear_button():
    if st.sidebar.button("🧹 XÓA BỘ NHỚ CACHE", use_container_width=True):
        st.cache_data.clear()
        st.sidebar.success("Đã làm sạch hệ thống!")

def render_search_and_export(results_df):
    # 1. Nếu dữ liệu rỗng, trả về nguyên bản
    if results_df is None or len(results_df) == 0:
        return results_df
        
    # 2. Tạo UI thanh tìm kiếm và nút tải file CSV
    col1, col2 = st.columns([3, 1])
    with col1:
        search_query = st.text_input("🔍 Nhập mã cổ phiếu cần tìm (VD: SSI, HPG):", "").upper()
    with col2:
        # Xử lý xuất file CSV
        csv_data = results_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Tải file (CSV)",
            data=csv_data,
            file_name="Danh_Sach_Co_Phieu.csv",
            mime="text/csv",
            use_container_width=True
        )
        
    # 3. Lọc dữ liệu nếu người dùng gõ tìm kiếm
    if search_query and 'Mã CK' in results_df.columns:
        results_df = results_df[results_df['Mã CK'].str.contains(search_query, case=False, na=False)]
            
    # CHỈ TRẢ VỀ DỮ LIỆU. TUYỆT ĐỐI KHÔNG DÙNG st.dataframe() Ở ĐÂY!
    return results_df
