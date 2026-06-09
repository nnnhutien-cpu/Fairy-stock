def render_screener_results(results_df, signal_filter):
    # Đảm bảo dữ liệu đầu vào luôn là DataFrame
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    
    # KHI CÓ DỮ LIỆU TỪ HỆ THỐNG TRUYỀN VÀO
    if not results_df.empty:
        
        # 1. BẢO VỆ LOGIC LỌC: Chỉ lọc khi người dùng chọn Tích cực/Tiêu cực (Bỏ qua "Tất cả")
        if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        # 2. KIỂM TRA LẠI: Nếu lọc xong mà bảng rỗng, cảnh báo và DỪNG CODE NGAY LẬP TỨC
        if results_df.empty:
            st.warning(f"⚠️ Không có mã cổ phiếu nào thỏa mãn tín hiệu '{signal_filter}'. Bạn hãy thử đổi bộ lọc nhé!")
            return pd.DataFrame() # <--- Lệnh ngắt sinh tử giúp app không bị sập!
        
        # 3. LỌC CỘT: Xóa cột 9 đáng ghét
        cols = [col for col in results_df.columns if str(col) != '9']
        
        # 4. SẮP XẾP: Đưa "Mã CK" lên vị trí số 1
        if 'Mã CK' in cols:
            cols.remove('Mã CK')
            cols = ['Mã CK'] + cols
        elif 'Mã' in cols:
            cols.remove('Mã')
            cols = ['Mã'] + cols

        df_display = results_df[cols]

        # 5. Hiển thị bảng
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # 6. Trả kết quả về cho main.py sử dụng (Giải quyết triệt để lỗi dòng 131)
        return df_display
        
    else:
        # KHI CHƯA BẤM NÚT QUÉT HOẶC VỪA XÓA CACHE
        st.info("Chưa có dữ liệu. Vui lòng bấm nút 'Lọc Cổ Phiếu' để bắt đầu!")
        return pd.DataFrame()
