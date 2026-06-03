import streamlit as st
import pandas as pd

def setup_cache_clear_button():
    """UX: Tạo nút xóa bộ nhớ đệm (Cache) ở thanh Sidebar"""
    with st.sidebar:
        st.divider()
        if st.button("🔄 Xóa bộ nhớ đệm (Tải dữ liệu mới)", use_container_width=True):
            st.cache_data.clear()
            st.toast("Đã dọn dẹp bộ nhớ đệm. Sẵn sàng quét dữ liệu mới nhất!", icon="🧹")

def render_search_and_export(results_list):
    """UX: Tạo thanh tìm kiếm nhanh và nút xuất Excel chống giật lag"""
    df_display = pd.DataFrame(results_list)
    
    if df_display.empty:
        return df_display
        
    col_search, col_dl = st.columns([3, 1])
    with col_search:
        # Gõ xong ấn Enter mới tìm kiếm để chống giật chớp màn hình
        search_kw = st.text_input(
            "🔍 Tìm kiếm nhanh mã cổ phiếu (Gõ xong nhấn Enter):", 
            placeholder="Ví dụ: VGI, HPG, SSI..."
        ).upper().strip()
        
    # Thuật toán lọc Real-time
    if search_kw:
        df_display = df_display[df_display['Mã'].str.contains(search_kw, na=False)]
        
    with col_dl:
        st.write("") # Khoảng trắng đẩy nút xuống cho bằng hàng với ô tìm kiếm
        st.write("") 
        if not df_display.empty:
            # Dùng utf-8-sig để Excel đọc tiếng Việt không bị lỗi font
            csv_data = df_display.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Xuất dữ liệu (Excel)", 
                data=csv_data, 
                file_name="Screener_Results.csv", 
                mime="text/csv", 
                use_container_width=True
            )
            
    return df_display
