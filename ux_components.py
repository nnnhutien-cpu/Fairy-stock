import streamlit as st
import pandas as pd

def setup_cache_clear_button():
    if st.sidebar.button("🧹 XÓA BỘ NHỚ CACHE", use_container_width=True):
        st.cache_data.clear()
        st.sidebar.success("Đã làm sạch toàn bộ hệ thống!")

# BÙA CHÚ CACHING CHO CSV: Giúp thanh tìm kiếm không bị giật lag khi gõ
@st.cache_data(show_spinner=False)
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

def render_search_and_export(results_df):
    # 1. Bảo vệ lỗi: Kiểm tra nếu dữ liệu rỗng hoặc không phải DataFrame
    if results_df is None or (isinstance(results_df, pd.DataFrame) and results_df.empty) or (isinstance(results_df, list) and len(results_df) == 0):
        return results_df
        
    # Đảm bảo dữ liệu luôn là Bảng Pandas để tránh lỗi
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
        
    # 2. Tạo UI thanh tìm kiếm và nút tải file CSV
    col1, col2 = st.columns([3, 1])
    with col1:
        # UX: Thanh tìm kiếm trực tiếp
        search_query = st.text_input("🔍 Nhập mã cổ phiếu cần tìm (VD: SSI, HPG):", "").upper()
    with col2:
        # Xử lý xuất file CSV siêu mượt nhờ gọi hàm đã Cache ở trên
        csv_data = convert_df_to_csv(results_df)
        st.download_button(
            label="📥 Tải file (CSV)",
            data=csv_data,
            file_name="Danh_Sach_Sieu_Co_Phieu.csv",
            mime="text/csv",
            use_container_width=True
        )
        
    # 3. Lọc dữ liệu theo thời gian thực (Sửa thành 'Mã CP' để khớp với indicators)
    if search_query and 'Mã CP' in results_df.columns:
        results_df = results_df[results_df['Mã CP'].str.contains(search_query, case=False, na=False)]
            
    # CHỈ TRẢ VỀ DỮ LIỆU. TUYỆT ĐỐI KHÔNG DÙNG st.dataframe() Ở ĐÂY!
    return results_df
