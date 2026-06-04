with tab_backtest:
    st.subheader("🛠️ Hệ Thống Thử Nghiệm Chiến Lược Ichimoku Khung 5 Phút")
    st.markdown("""
    * **Chiến lược áp dụng:**
        * 🟢 **Tín hiệu MUA:** Giá đóng cửa cắt lên trên biên trên của Mây Kumo (**Cloud Top**).
        * 🔴 **Tín hiệu BÁN:** Giá đóng cửa cắt xuống dưới biên dưới của Mây Kumo (**Cloud Bottom**).
    """)

    # 1. Khởi tạo form nhập thông số đầu vào cho Backtest
    col_bt1, col_bt2, col_bt3 = st.columns(3)
    with col_bt1:
        bt_ticker = st.text_input("🔤 Nhập mã cổ phiếu thử nghiệm:", value="CEO").upper().strip()
    with col_bt2:
        bt_capital = st.number_input("💰 Vốn đầu tư ban đầu (VNĐ):", min_value=10000000, value=100000000, step=10000000, format="%d")
    with col_bt3:
        bt_days = st.slider("📅 Khoảng thời gian khảo sát (Số ngày về trước):", min_value=1, max_value=60, value=30)

    # Nút kích hoạt lệnh chạy
    btn_run_bt = st.button("🎯 KÍCH HOẠT BACKTEST TOÀN DIỆN", use_container_width=True, type="primary")

    if btn_run_bt:
        if not bt_ticker:
            st.error("⚠️ Lỗi: Bạn chưa điền mã cổ phiếu!")
        else:
            with st.status(f"⚡ Đang kéo dữ liệu intraday và chạy mô phỏng mã {bt_ticker}...", expanded=True) as status:
                
                # Bước 1: Gọi hàm lấy dữ liệu nến 5P trực tiếp từ API trong file backtester
                df_raw = bt.get_5m_data(bt_ticker, days_back=bt_days)
                
                if df_raw is None or df_raw.empty:
                    st.error(f"⚠️ Lỗi mạng hoặc mã {bt_ticker} không tồn tại. Vui lòng kiểm tra lại!")
                    status.update(label="Backtest thất bại!", state="error")
                else:
                    # Bước 2: Tính chỉ báo Ichimoku lấy từ các thông số cấu hình ĐỘNG bên Sidebar
                    df_indicators = bt.calculate_ichimoku_3m(
                        df_raw, 
                        p_tenkan=p_tenkan, 
                        p_kijun=p_kijun, 
                        p_senkou_b=p_senkou_b, 
                        p_shift=p_shift
                    )
                    
                    if df_indicators is None or df_indicators.empty:
                        st.warning("⚠️ Tập dữ liệu quá ngắn, không đủ để hình thành Mây Ichimoku. Vui lòng tăng số ngày khảo sát!")
                        status.update(label="Thiếu dữ liệu dựng chỉ báo!", state="value_error")
                    else:
                        # Bước 3: Đẩy vào bộ máy Backtest tính toán lợi nhuận
                        stats, trade_log = bt.run_ichimoku_backtest(df_indicators, initial_capital=bt_capital)
                        
                        status.update(label="🎯 Đã xử lý xong dữ liệu giao dịch!", state="complete")
                        
                        # ---- HIỂN THỊ KẾT QUẢ RA GIAO DIỆN ----
                        st.success(f"🎉 Kết quả Backtest chiến lược mã: {bt_ticker} (Khung 5 Phút)")
                        
                        # Tạo các ô số liệu tổng quan (Metrics)
                        m1, m2, m3, m4, m5 = st.columns(5)
                        m1.metric("💵 Vốn đầu vào", stats["Vốn ban đầu"])
                        m2.metric("💰 Vốn cuối kỳ", stats["Vốn cuối kỳ"])
                        m3.metric("📈 Lợi nhuận ròng", stats["Lợi nhuận ròng"])
                        m4.metric("📊 Tổng số lệnh", stats["Tổng số lệnh (Cặp Mua/Bán)"])
                        m5.metric("🎯 Tỷ lệ Thắng", stats["Tỷ lệ Thắng (Win Rate)"])
                        
                        # Bảng hiển thị Nhật ký lịch sử mua bán chi tiết
                        st.subheader("📋 Nhật Ký Lịch Sử Giao Dịch Chi Tiết (Trade Log)")
                        if not trade_log.empty:
                            # Sao chép bảng để định dạng hiển thị đẹp mắt hơn mà không làm hỏng dữ liệu gốc
                            display_log = trade_log.copy()
                            
                            # Định dạng tiền tệ và tỷ lệ phần trăm cho dễ nhìn
                            if 'Price' in display_log.columns:
                                display_log['Price'] = display_log['Price'].map('{:,.2f}'.format)
                            if 'Total Capital' in display_log.columns:
                                display_log['Total Capital'] = display_log['Total Capital'].map('{:,.0f} VNĐ'.format)
                                
                            st.dataframe(display_log, use_container_width=True)
                            
                            # Cho phép người dùng xuất file Excel/CSV nhật ký để nghiên cứu sâu
                            csv_data = trade_log.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Xuất Nhật Ký Giao Dịch Sang File CSV",
                                data=csv_data,
                                file_name=f"Backtest_Ichimoku_5M_{bt_ticker}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        else:
                            st.info("ℹ️ Không tìm thấy bất kỳ tín hiệu Mua/Bán nào được kích hoạt trong khoảng thời gian này.")
