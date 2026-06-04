import chart as c  # [MỚI] Gọi file gánh biểu đồ phân tầng
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
# ==========================================
# TAB 3: MÔ PHỎNG ICHIMOKU REAL-TIME & VOLUME
# ==========================================
with tab_simulation:
    st.subheader("🔮 Hệ Thống Mô Phỏng & Trực Quan Hóa Mây Ichimoku Nâng Cao")
    st.markdown("* **Hỗ trợ thực chiến:** Tự động đồng bộ cấu hình chỉ báo động từ Sidebar và bóc tách khối lượng dòng tiền phân tầng.")
    
    sim_col1, sim_col2 = st.columns([1, 3])
    with sim_col1:
        sim_ticker = st.text_input("🔤 Nhập mã CK cần mô phỏng:", value="SSI", key="sim_input_unique").upper().strip()
        sim_btn = st.button("📈 VẼ ĐỒ THỊ KỸ THUẬT ĐA TẦNG", use_container_width=True, type="primary")
        
    if sim_btn:
        if not sim_ticker:
            st.warning("⚠️ Vui lòng điền mã cổ phiếu trước khi kích hoạt!")
        else:
            with st.spinner(f"⚡ Đang cào dữ liệu nến 5P và dựng cấu trúc mây {sim_ticker}..."):
                # Kéo dữ liệu 5 phút (lấy 5 ngày cho nhẹ máy và dư phiên tính toán)
                df_sim = bt.get_5m_data(sim_ticker, days_back=5)
                
                if df_sim is not None and not df_sim.empty:
                    # Tính toán mây Ichimoku dựa trên thông số Sidebar
                    df_ichimoku = bt.calculate_ichimoku_5m(
                        df_sim, 
                        p_tenkan=p_tenkan, 
                        p_kijun=p_kijun, 
                        p_senkou_b=p_senkou_b, 
                        p_shift=p_shift
                    )
                    
                    if df_ichimoku is not None and not df_ichimoku.empty:
                        latest = df_ichimoku.iloc[-1]
                        
                        st.success(f"🎉 Đồng bộ thành công dữ liệu Real-time mã: {sim_ticker}")
                        
                        # Hiển thị thanh số liệu nhanh (Metrics Dashboard) có cột Dòng tiền Volume
                        m1, m2, m3, m4 = st.columns(4)
                        close_price = float(latest.get('close', 0))
                        volume = float(latest.get('volume', 0))
                        tenkan = float(latest.get('tenkan', 0))
                        kijun = float(latest.get('kijun', 0))
                        cloud_top = float(latest.get('cloud_top', 0))
                        cloud_bottom = float(latest.get('cloud_bottom', 0))
                        
                        prev_close = float(df_ichimoku.iloc[-2]['close']) if len(df_ichimoku) > 1 else close_price
                        price_change = close_price - prev_close
                        
                        m1.metric("🔴 Giá Khớp Lệnh Hiện Tại", f"{close_price:,.2f}", delta=f"{price_change:,.2f}" if price_change != 0 else None)
                        m2.metric("📊 Vol Cây Nến 5P Vừa Qua", f"{volume:,.0f}")
                        m3.metric("🔵 Tenkan / 🟡 Kijun", f"{tenkan:,.2f} / {kijun:,.2f}")
                        m4.metric("☁️ Biên Mây (Top/Bottom)", f"{cloud_top:,.2f} / {cloud_bottom:,.2f}")
                        
                        # 🚀 ĐOẠN ĐỈNH CAO CHẤT LƯỢNG: Ủy thác toàn bộ việc vẽ đồ thị cho file chart.py gánh vác
                        st.markdown("### 📊 Đồ Thị Phân Tích Kỹ Thuật Phân Tầng (Giá & Volume Dòng Tiền)")
                        c.render_ichimoku_simulation_chart(df_ichimoku)
                    else:
                        st.warning("⚠️ Tập dữ liệu không đủ dài để dựng mây Ichimoku. Vui lòng thử lại!")
                else:
                    st.error("⚠️ Không kéo được dữ liệu. Mã CK có thể sai hoặc hệ thống API quá tải!")

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
                            
                            # --- 1. PHẦN MỚI: Định dạng số liệu hiển thị trên Web cho đẹp ---
                            if 'Giá khớp' in display_log.columns:
                                display_log['Giá khớp'] = display_log['Giá khớp'].map('{:,.2f}'.format)
                            if 'Vol nến 5P' in display_log.columns:
                                display_log['Vol nến 5P'] = display_log['Vol nến 5P'].map('{:,.0f}'.format)
                            if 'Khối lượng nắm giữ' in display_log.columns:
                                display_log['Khối lượng nắm giữ'] = display_log['Khối lượng nắm giữ'].map('{:,.0f}'.format)
                            if 'Vốn khả dụng' in display_log.columns:
                                display_log['Vốn khả dụng'] = display_log['Vốn khả dụng'].map('{:,.0f} VNĐ'.format)
                                
                            st.dataframe(display_log, use_container_width=True, hide_index=True)
                            
                            # --- 2. PHẦN CŨ (GIỮ NGUYÊN): Nút xuất file CSV ---
                            # Mẹo nhỏ: Tôi đổi 'utf-8' thành 'utf-8-sig' để khi mở bằng Excel không bị lỗi font Tiếng Việt
                            csv_data = trade_log.to_csv(index=False).encode('utf-8-sig')
                            st.download_button(
                                label="📥 Xuất Nhật Ký Giao Dịch Sang File CSV",
                                data=csv_data,
                                file_name=f"Backtest_Ichimoku_5M_{bt_ticker}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        else:
                            st.info("ℹ️ Không tìm thấy bất kỳ tín hiệu Mua/Bán nào được kích hoạt trong khoảng thời gian này.")
                            st.info("ℹ️ Không tìm thấy bất kỳ tín hiệu Mua/Bán nào được kích hoạt trong khoảng thời gian này.")
