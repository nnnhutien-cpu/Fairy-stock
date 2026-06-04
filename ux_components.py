import streamlit as st
import pandas as pd
import time

def setup_cache_clear_button():
    """
    Nút dọn rác bộ nhớ: Giúp giải phóng RAM khi app chạy liên tục 4 Tabs
    tránh hiện tượng sập Web (Out of Memory) trên Streamlit Cloud.
    """
    with st.sidebar:
        st.markdown("---") # Đường kẻ phân cách cho đẹp
        # Dùng type="secondary" để nút không tranh giành sự chú ý với các nút chính
        if st.button("🧹 Dọn Rác & Tải Lại", use_container_width=True, type="secondary"):
            # Xóa cả data và resource cache để triệt để
            st.cache_data.clear()
            if hasattr(st, 'cache_resource'):
                st.cache_resource.clear()
                
            # [UX MỚI] Hiển thị thông báo nổi (Toast) góc dưới màn hình
            st.toast("✅ Đã giải phóng bộ nhớ! Ứng dụng sẽ chạy mượt hơn.", icon="🚀")
            time.sleep(1) # Dừng 1 giây để user kịp đọc thông báo rồi mới f5
            st.rerun()

def render_search_and_export(results_list, filename="Dulieu_Chungkhoan.csv"):
    """
    Thanh công cụ UX thông minh: Khung tìm kiếm Real-time, đếm số lượng, 
    xuất file chống lỗi Font và cố định chiều cao bảng chống giật lag.
    """
    # 1. Bẫy lỗi: Rỗng thì không render bảng để tiết kiệm tài nguyên
    if not results_list:
        return None
        
    df_display = pd.DataFrame(results_list)
    if df_display.empty:
        return df_display
    
    # 2. Bố cục thanh công cụ (Toolbar)
    col_search, col_export, col_stats = st.columns([5, 2, 2])
    
    with col_search:
        # Nhập liệu không cần nhấn Enter, Streamlit tự lọc ngay khi gõ
        search = st.text_input("🔍 Tìm nhanh (Mã CK, Trạng thái, v.v.):", placeholder="VD: HPG hoặc MUA...")
        
    with col_export:
        # Căn chỉnh CSS thủ công đẩy nút bấm chìm xuống bằng hàng với ô tìm kiếm
        st.write("") 
        st.write("")
        # [TỐI ƯU UX] Dùng utf-8-sig để khi mở Excel ra chữ Tiếng Việt không bị loằng ngoằng
        csv = df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Xuất Excel", csv, filename, use_container_width=True)
        
    # 3. Logic Lọc dữ liệu Đa Năng (Tìm trên mọi cột thay vì chỉ cột 'Mã')
    if search:
        # Chuyển về string và tìm kiếm không phân biệt chữ hoa/chữ thường (case=False)
        mask = df_display.astype(str).apply(lambda x: x.str.contains(search, case=False, na=False)).any(axis=1)
        df_filtered = df_display[mask]
    else:
        df_filtered = df_display
        
    with col_stats:
        st.write("")
        st.write("")
        # Báo cáo nhanh cho người dùng biết họ đang xem bao nhiêu mã
        st.caption(f"📊 Hiển thị: **{len(df_filtered)} / {len(df_display)}** dòng")

    # 4. Render Bảng dữ liệu chống giật lag
    # Thay vì st.write hay st.table, st.dataframe của bản Streamlit mới được tối ưu Canvas rất nhẹ
    st.dataframe(
        df_filtered,
        use_container_width=True,
        hide_index=True, # Tắt cột số thứ tự 0,1,2,3 mặc định của Pandas cho đỡ rối mắt
        height=500 # Cố định chiều cao 500px để khi cuộn chuột khung web không bị giật lên giật xuống
    )
    
    return df_filtered
