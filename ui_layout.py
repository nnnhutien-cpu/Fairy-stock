def render_screener_results(results, signal_filter):
    if results:
        # Chuyển list kết quả thành DataFrame
        results_df = pd.DataFrame(results)
        
        # Lọc trạng thái Tích cực/Tiêu cực
        if signal_filter != "Tất cả":
            results_df = results_df[results_df['Trạng thái'] == signal_filter]
        
        if not results_df.empty:
            # 🛠️ Sắp xếp cột: Đã loại bỏ hoàn toàn P/E, P/B và cố định vị trí Vốn hóa lưu hành
            cols_order = [
                "Mã", "Giá", "GTGD (Tỷ)", "Khối Lượng", "KL TB 20 Phiên",
                "Vốn hóa lưu hành", "Đánh Giá", 
                "Tenkan", "Kijun", "Senkou A", "Senkou B", "Chikou", 
                "Ichimoku_Cloud", "Trạng thái"
            ]
            # Chỉ lấy các cột tồn tại để tránh lỗi
            results_df = results_df[[c for c in cols_order if c in results_df.columns]]
            
            st.dataframe(
                results_df, use_container_width=True, hide_index=True,
                column_config={
                    # 🛠️ Sử dụng %,d và %,.2f để tự động thêm dấu phẩy ngăn cách hàng nghìn
                    "Khối Lượng": st.column_config.NumberColumn(format="%,d"),
                    "KL TB 20 Phiên": st.column_config.NumberColumn(format="%,d"),
                    "Giá": st.column_config.NumberColumn(format="%,.2f"),
                    "GTGD (Tỷ)": st.column_config.NumberColumn(format="%,.2f"),
                    "Vốn hóa lưu hành": st.column_config.NumberColumn(format="%,.2f"), 
                    "Tenkan": st.column_config.NumberColumn(format="%,.2f"),
                    "Kijun": st.column_config.NumberColumn(format="%,.2f"),
                    "Senkou A": st.column_config.NumberColumn(format="%,.2f"),
                    "Senkou B": st.column_config.NumberColumn(format="%,.2f"),
                    "Chikou": st.column_config.NumberColumn(format="%,.2f")
                }
            )
            st.toast("Đã hiển thị danh sách lọc cổ phiếu thành công!", icon="🧚‍♀️")
        else:
            st.info(f"Không có mã nào thuộc nhóm '{signal_filter}' đạt điều kiện.")
    else:
        st.info("Chưa tìm thấy mã nào đạt điều kiện thanh khoản.")
