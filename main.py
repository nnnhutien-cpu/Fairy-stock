import streamlit as st
import pandas as pd
import concurrent.futures
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt 

# 1. Cấu hình trang
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

# 2. Khởi tạo Sidebar và Nút xóa Cache
exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()
setup_cache_clear_button()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật")

# 3. Khai sinh 4 Tabs
tab_market, tab_screener, tab_simulation, tab_backtest = st.tabs([
    "📊 TỔNG QUAN VN-INDEX", 
    "🚀 BỘ LỌC CỔ PHIẾU", 
    "🔮 MÔ PHỎNG ICHIMOKU",
    "🛠️ BACKTEST KHUNG 5P"
])

# ==========================================
# TAB 1: THỊ TRƯỜNG CHUNG
# ==========================================
with tab_market:
    intraday_df = get_intraday_vnindex()
    chart_df, df_today = None, None

    if intraday_df is not None and not intraday_df.empty:
        col_mapping = {}
        for col in intraday_df.columns:
            lower_col = str(col).lower().strip()
            if lower_col in ['close', 'price', 'c', 'điểm', 'index', 'indexvalue']:
                col_mapping[col] = 'close'
            elif lower_col in ['volume', 'vol', 'v', 'khối lượng', 'matchvolume']:
                col_mapping[col] = 'volume'
            elif lower_col in ['time', 't', 'thời gian']:
                col_mapping[col] = 'time'
        
        intraday_df.rename(columns=col_mapping, inplace=True)
        
        if 'time' in intraday_df.columns and 'volume' in intraday_df.columns:
            intraday_df['volume'] = pd.to_numeric(intraday_df['volume'], errors='coerce').fillna(0)
            intraday_df['time'] = pd.to_datetime(intraday_df['time'])
            intraday_df['date'] = intraday_df['time'].dt.date
            intraday_df['hour_min'] = intraday_df['time'].dt.strftime('%H:%M')
            
            dates = intraday_df['date'].unique()
            if len(dates) >= 2:
                today_date = dates[-1]
                yest_date = dates[-2]
                
                df_today = intraday_df[intraday_df['date'] == today_date].copy()
                df_yest = intraday_df[intraday_df['date'] == yest_date].copy()
                
                df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
                df_yest['Vol_Hôm_Qua'] = df_yest['volume'].cumsum()
                
                chart_df = pd.merge(df_yest[['hour_min', 'Vol_Hôm_Qua']], 
                                    df_today[['hour_min', 'Vol_Hôm_Nay']], 
                                    on='hour_min', how='outer').sort_values('hour_min')
                
                chart_df['Vol_Hôm_Qua'] = chart_df['Vol_Hôm_Qua'].ffill()
                chart_df['Vol_Hôm_Nay'] = chart_df['Vol_Hôm_Nay'].ffill()
                chart_df.set_index('hour_min', inplace=True)
    else:
        st.warning("⚠️ Đang chờ dữ liệu VN-INDEX từ API. Vui lòng tải lại trang sau ít phút...")
            
    render_market_tab(chart_df, df_today)

# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU ĐA LUỒNG
# ==========================================
with tab_screener:
    st.subheader(f"Danh Sách Quét Sàn {exchange_choice} (>20 Tỷ VNĐ)")
    scan_button = st.button("🚀 KÍCH HOẠT QUÉT TOÀN DIỆN", use_container_width=True, type="primary")
    
    if scan_button:
        ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
        tickers = get_all_tickers(ex_code)
        
        if tickers is None or len(tickers) == 0:
            st.error("⚠️ Lỗi mạng: Không lấy được danh sách mã chứng khoán!")
        else:
            tickers_to_scan = tickers[:max_scan]
            
            with st.status(f"Đang dùng 10 Luồng quét {len(tickers_to_scan)} mã. Tốc độ siêu tốc...", expanded=True) as status:
                progress_bar = st.progress(0)
                results = []
                total = len(tickers_to_scan)
                processed = 0

                def process_ticker(ticker):
                    try:
                        df = get_stock_data(ticker)
                        if df is not None and not df.empty:
                            signals = calculate_technical_signals(df, p_tenkan, p_kijun, p_senkou_b, p_shift)
                            if signals: 
                                return {"Mã CK": ticker, "Tín hiệu": signals, "Trạng thái": "Thành công"}
                    except Exception as e:
                        return {"Mã CK": ticker, "Lỗi": str(e), "Trạng thái": "Lỗi"}
                    return None

                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}
                    for future in concurrent.futures.as_completed(future_to_ticker):
                        res = future.result()
                        if res:
                            results.append(res)
                        processed += 1
                        progress_bar.progress(processed / total)
                
                status.update(label=f"✅ Đã quét xong {total} mã chứng khoán!", state="complete")
                st.session_state['scan_results'] = results

    # Render dữ liệu bằng hàm UX mới tối ưu (Có Search & Tự cố định chiều cao)
    if st.session_state['scan_results']:
        render_search_and_export(st.session_state['scan_results'])

# ==========================================
# TAB 3: MÔ PHỎNG ICHIMOKU
# ==========================================
# ==========================================
# TAB 3: MÔ PHỎNG ICHIMOKU
# ==========================================
with tab_simulation:
    st.subheader("🔮 Hệ Thống Mô Phỏng & Trực Quan Hóa Mây Ichimoku")
    
    sim_col1, sim_col2 = st.columns([1, 3])
    with sim_col1:
        sim_ticker = st.text_input("🔤 Nhập mã CK cần xem:", value="SSI", key="sim_input").upper().strip()
        sim_btn = st.button("📈 VẼ ĐỒ THỊ MÂY", use_container_width=True, type="primary")
        
    if sim_btn:
        if not sim_ticker:
            st.warning("⚠️ Vui lòng nhập mã chứng khoán!")
        else:
            with st.spinner(f"Đang tính toán mây Kumo cho {sim_ticker}..."):
                # 1. Tận dụng hàm bốc dữ liệu từ data_loader
                df_sim = get_stock_data(sim_ticker)
                
                if df_sim is not None and not df_sim.empty:
                    # 2. Đưa vào hàm tính toán Ichimoku (Dùng chung hàm bên file backtester)
                    # Truyền các thông số động lấy từ Sidebar vào
                    df_ichimoku = bt.calculate_ichimoku_5m(
                        df_sim, 
                        p_tenkan=p_tenkan, 
                        p_kijun=p_kijun, 
                        p_senkou_b=p_senkou_b, 
                        p_shift=p_shift
                    )
                    
                    if df_ichimoku is not None and not df_ichimoku.empty:
                        latest = df_ichimoku.iloc[-1]
                        
                        st.success(f"✅ Phân tích thành công! Trạng thái hiện tại của {sim_ticker}:")
                        
                        # 3. Hiển thị bảng Dashboard thông số hiện tại
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("🔴 Giá Đóng Cửa", f"{latest['close']:,.2f}")
                        m2.metric("🔵 Tenkan (Đường chuyển)", f"{latest['tenkan']:,.2f}")
                        m3.metric("🟡 Kijun (Đường chuẩn)", f"{latest['kijun']:,.2f}")
                        m4.metric("☁️ Viền Mây (Top/Bottom)", f"{latest['cloud_top']:,.2f} / {latest['cloud_bottom']:,.2f}")
                        
                        # 4. Trực quan hóa bằng biểu đồ siêu mượt của Streamlit
                        st.markdown("### 📊 Biểu đồ Xu Hướng Giá & Cấu Trúc Mây")
                        
                        # Chỉ lọc ra các đường cần thiết để vẽ đồ thị
                        chart_data = df_ichimoku.set_index('time')[['close', 'tenkan', 'kijun', 'senkou_a', 'senkou_b']]
                        st.line_chart(chart_data)
                    else:
                        st.warning("⚠️ Tập dữ liệu không đủ dài (Cần ít nhất 52 phiên) để hình thành Mây Kumo.")
                else:
                    st.error("⚠️ Lỗi mạng hoặc không tìm thấy mã chứng khoán này trên hệ thống!")

# ==========================================
# TAB 4: BACKTEST KHUNG 5 PHÚT
# ==========================================
with tab_backtest:
    st.subheader("🛠️ Hệ Thống Thử Nghiệm Chiến Lược Ichimoku Khung 5 Phút")
    st.markdown("""
    * **Chiến lược áp dụng:**
        * 🟢 **Tín hiệu MUA:** Giá đóng cửa cắt lên trên biên trên của Mây Kumo (**Cloud Top**).
        * 🔴 **Tín hiệu BÁN:** Giá đóng cửa cắt xuống dưới biên dưới của Mây Kumo (**Cloud Bottom**).
    """)

    col_bt1, col_bt2, col_bt3 = st.columns(3)
    with col_bt1:
        bt_ticker = st.text_input("🔤 Nhập mã cổ phiếu thử nghiệm:", value="CEO").upper().strip()
    with col_bt2:
        bt_capital = st.number_input("💰 Vốn đầu tư ban đầu (VNĐ):", min_value=10000000, value=100000000, step=10000000, format="%d")
    with col_bt3:
        bt_days = st.slider("📅 Khoảng thời gian khảo sát (Số ngày về trước):", min_value=1, max_value=60, value=30)

    btn_run_bt = st.button("🎯 KÍCH HOẠT BACKTEST TOÀN DIỆN", use_container_width=True, type="primary")

    if btn_run_bt:
        if not bt_ticker:
            st.error("⚠️ Lỗi: Bạn chưa điền mã cổ phiếu!")
        else:
            with st.status(f"⚡ Đang kéo dữ liệu intraday và chạy mô phỏng mã {bt_ticker}...", expanded=True) as status:
                df_raw = bt.get_5m_data(bt_ticker, days_back=bt_days)
                
                if df_raw is None or df_raw.empty:
                    st.error(f"⚠️ Lỗi mạng hoặc mã {bt_ticker} không tồn tại. Vui lòng kiểm tra lại!")
                    status.update(label="Backtest thất bại!", state="error")
                else:
                    df_indicators = bt.calculate_ichimoku_5m(
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
                        stats, trade_log = bt.run_ichimoku_backtest(df_indicators, initial_capital=bt_capital)
                        status.update(label="🎯 Đã xử lý xong dữ liệu giao dịch!", state="complete")
                        
                        st.success(f"🎉 Kết quả Backtest chiến lược mã: {bt_ticker} (Khung 5 Phút)")
                        
                        m1, m2, m3, m4, m5 = st.columns(5)
                        m1.metric("💵 Vốn đầu vào", stats["Vốn ban đầu"])
                        m2.metric("💰 Vốn cuối kỳ", stats["Vốn cuối kỳ"])
                        m3.metric("📈 Lợi nhuận ròng", stats["Lợi nhuận ròng"])
                        m4.metric("📊 Tổng số lệnh", stats["Tổng số lệnh (Cặp Mua/Bán)"])
                        m5.metric("🎯 Tỷ lệ Thắng", stats["Tỷ lệ Thắng (Win Rate)"])
                        
                        st.subheader("📋 Nhật Ký Lịch Sử Giao Dịch Chi Tiết (Trade Log)")
                        if not trade_log.empty:
                            display_log = trade_log.copy()
                            
                            if 'Price' in display_log.columns:
                                display_log['Price'] = display_log['Price'].map('{:,.2f}'.format)
                            if 'Total Capital' in display_log.columns:
                                display_log['Total Capital'] = display_log['Total Capital'].map('{:,.0f} VNĐ'.format)
                                
                            st.dataframe(display_log, use_container_width=True)
                            
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
