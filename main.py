import streamlit as st
import pandas as pd
import concurrent.futures
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export # Gọi file UX
import backtester as bt # [CẬP NHẬT] Nhập file backtest khung ngày (1DAY)

st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

# Đọc các thông số Ichimoku động từ Sidebar bên trái
exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()

# [GỌI HÀM UX] Tạo nút xóa Cache
setup_cache_clear_button()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật")

# [ĐỒNG BỘ CHUẨN] Đổi tên Tab thứ 4 thành Khung Ngày 1DAY theo đúng logic code
tab_market, tab_screener, tab_simulation, tab_backtest = st.tabs([
    "📊 TỔNG QUAN VN-INDEX", 
    "🚀 BỘ LỌC CỔ PHIẾU", 
    "🔮 MÔ PHỎNG ICHIMOKU",
    "🛠️ BACKTEST KHUNG 1DAY"
])

# ==========================================
# TAB 1: THỊ TRƯỜNG CHUNG
# ==========================================
with tab_market:
    # --- NÚT BẤM CẬP NHẬT REAL-TIME ---
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("🌟 TỔNG QUAN THỊ TRƯỜNG REAL-TIME")
    with col_btn:
        if st.button("🔄 CẬP NHẬT DỮ LIỆU", type="primary", use_container_width=True):
            get_intraday_vnindex.clear()
            st.rerun() 
    st.divider()
    # ---------------------------------------

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
        
        # Đảm bảo có đủ 3 cột: time, volume và close
        if 'time' in intraday_df.columns and 'volume' in intraday_df.columns and 'close' in intraday_df.columns:
            intraday_df['volume'] = pd.to_numeric(intraday_df['volume'], errors='coerce').fillna(0)
            intraday_df['close'] = pd.to_numeric(intraday_df['close'], errors='coerce').fillna(0)
            intraday_df['time'] = pd.to_datetime(intraday_df['time'])
            intraday_df['date'] = intraday_df['time'].dt.date
            intraday_df['hour_min'] = intraday_df['time'].dt.strftime('%H:%M')
            
            # ✂️ LƯỚI LỌC THỜI GIAN: Chặt bỏ rác, chỉ giữ đúng phiên giao dịch (09:00 - 15:15) cho toàn bộ tập dữ liệu
            intraday_df = intraday_df[(intraday_df['hour_min'] >= '09:00') & (intraday_df['hour_min'] <= '15:15')]
            
            dates = intraday_df['date'].unique()
            if len(dates) >= 2:
                today_date = dates[-1]
                yest_date = dates[-2]
                
                df_today = intraday_df[intraday_df['date'] == today_date].copy()
                df_yest = intraday_df[intraday_df['date'] == yest_date].copy()
                
                df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
                df_yest['Vol_Hôm_Qua'] = df_yest['volume'].cumsum()
                
                # Lấy chỉ số chốt cuối cùng
                current_index = df_today['close'].iloc[-1] if not df_today.empty else 0
                prev_index = df_yest['close'].iloc[-1] if not df_yest.empty else current_index
                index_change = current_index - prev_index
                
                # Lấy tổng khối lượng: Hôm nay (tính đến hiện tại) so với Hôm qua (Chốt phiên 15:15)
                current_vol = df_today['Vol_Hôm_Nay'].iloc[-1] if not df_today.empty else 0
                prev_vol = df_yest['Vol_Hôm_Qua'].iloc[-1] if not df_yest.empty else 0
                vol_change = current_vol - prev_vol
                
                # In ra 3 khối Metric đẹp mắt
                m1, m2, m3 = st.columns(3)
                m1.metric("📊 Chỉ số VN-INDEX", f"{current_index:,.2f} đ", f"{index_change:,.2f} đ")
                m2.metric("💰 Thanh khoản Hôm Nay", f"{current_vol:,.0f} CP", f"{vol_change:,.0f} CP" if vol_change != 0 else None)
                m3.metric("⏳ Thanh khoản Hôm Qua (EOD)", f"{prev_vol:,.0f} CP")
                
                # Tạo bảng ghép chung 2 ngày để vẽ biểu đồ cắt nhau
                chart_df = pd.merge(df_yest[['hour_min', 'Vol_Hôm_Qua']], 
                                    df_today[['hour_min', 'Vol_Hôm_Nay']], 
                                    on='hour_min', how='outer').sort_values('hour_min')
                
                chart_df['Vol_Hôm_Qua'] = chart_df['Vol_Hôm_Qua'].ffill()
                chart_df['Vol_Hôm_Nay'] = chart_df['Vol_Hôm_Nay'].ffill()
                chart_df.set_index('hour_min', inplace=True)
    else:
        st.warning("⚠️ Đang chờ dữ liệu VN-INDEX từ API. Vui lòng tải lại trang sau ít phút...")
            
    render_market_tab(chart_df, df_today)

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
            
            # UX: Báo cáo trạng thái rõ ràng, không làm người dùng hoang mang
            with st.status(f"Đang dùng 15 Luồng an toàn quét {len(tickers_to_scan)} mã (Dữ liệu Daily 365 ngày)...", expanded=True) as status:
                progress_bar = st.progress(0)
                results = []
                total = len(tickers_to_scan)
                processed = 0

                def process_ticker(ticker):
                    # Cache dữ liệu ở data_loader sẽ giúp đoạn này chạy siêu tốc
                    df = get_stock_data(ticker, days_back=365) # Lấy 365 ngày
                    if df is None or df.empty:
                        return None
                    return calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)

                # Giảm max_workers xuống 15 để không bị nghẽn mạng!
                with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                    future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}
                    for future in concurrent.futures.as_completed(future_to_ticker):
                        processed += 1
                        try:
                            res = future.result()
                            if res is not None:
                                results.append(res)
                        except Exception:
                            pass
                        # Cập nhật thanh UX mượt mà
                        progress_bar.progress(processed / total)
                
                status.update(label=f"✅ Đã quét xong siêu tốc và an toàn!", state="complete", expanded=False)
            st.session_state['scan_results'] = results
    
    if st.session_state['scan_results']:
        st.divider()
        
        # Ép danh sách (List) biến thành Bảng Pandas (DataFrame) trước
        raw_df = pd.DataFrame(st.session_state['scan_results'])
        
        # Đưa bảng chuẩn vào hàm UX để hiển thị thanh tìm kiếm và nút tải xuống
        df_display = render_search_and_export(raw_df)
        
        render_screener_results(df_display, signal_filter)
    else:
        st.caption(f"Hãy cấu hình thông số ở Sidebar trái và bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' để bắt đầu.")

with tab_simulation:
    st.subheader("🔮 Phòng Thí Nghiệm Chỉ Báo Kỹ Thuật Ichimoku")
    st.caption("Nhập một mã cổ phiếu bất kỳ để hệ thống tự động vẽ đồ thị phân rã toàn bộ 5 đường Ichimoku dựa trên thông số gạt ở Sidebar trái.")
    
    sim_ticker = st.text_input("Nhập mã cổ phiếu (Gõ xong nhấn Enter):", value="HPG").upper().strip()
    
    if sim_ticker:
        with st.spinner(f"Đang tải dữ liệu mô phỏng cho {sim_ticker}..."): 
            df_sim = get_stock_data(sim_ticker)
            
            if df_sim is not None and not df_sim.empty:
                df_sim.columns = [str(c).lower().strip() for c in df_sim.columns]
                
                df_sim['Tenkan'] = (df_sim['high'].rolling(window=p_tenkan).max() + df_sim['low'].rolling(window=p_tenkan).min()) / 2
                df_sim['Kijun'] = (df_sim['high'].rolling(window=p_kijun).max() + df_sim['low'].rolling(window=p_kijun).min()) / 2
                
                senkou_a_raw = (df_sim['Tenkan'] + df_sim['Kijun']) / 2
                df_sim['Senkou A'] = senkou_a_raw.shift(p_shift)
                
                senkou_b_raw = (df_sim['high'].rolling(window=p_senkou_b).max() + df_sim['low'].rolling(window=p_senkou_b).min()) / 2
                df_sim['Senkou B'] = senkou_b_raw.shift(p_shift)
                
                df_sim['Chikou'] = df_sim['close']
                
                plot_df = df_sim.tail(60).copy()
                
                if 'time' in plot_df.columns:
                    plot_df['Ngay'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
                    plot_df.set_index('Ngay', inplace=True)
                
                chart_data = plot_df[['close', 'Tenkan', 'Kijun', 'Senkou A', 'Senkou B']]
                chart_data.columns = ['Giá Hiện Tại', 'Tenkan (Chuyển đổi)', 'Kijun (Cơ sở)', 'Senkou A (Biên mây 1)', 'Senkou B (Biên mây 2)']
                
                plot_df['Màu Sắc'] = ['#00C853' if c >= o else '#FF1744' for c, o in zip(plot_df['close'], plot_df['open'])]
                plot_df['Khối Lượng'] = plot_df['volume']
                
                st.markdown(f"**📈 Đồ thị Đường Giá & Mây Ichimoku mã {sim_ticker}**")
                st.line_chart(chart_data, height=400)
                
                st.markdown(f"**📊 Khối Lượng Giao Dịch (Volume)**")
                st.bar_chart(plot_df, y='Khối Lượng', color='Màu Sắc', height=150)
                
                st.info(f"💡 **Mẹo thực chiến cho mã {sim_ticker}:** Hãy thử thay đổi thông số nâng cao ở Sidebar trái, đồ thị trên sẽ lập tức biến đổi Real-time để bạn tìm ra bộ khung chu kỳ tối ưu nhất cho riêng mình!")
            else:
                st.error(f"⚠️ Không thể kết nối hoặc không tìm thấy dữ liệu lịch sử của mã '{sim_ticker}'. Vui lòng thử lại mã khác.")

# Tích hợp Tab 4: Hệ thống Backtest Cổ Phiếu Khung Ngày (Daily) hoàn chỉnh
with tab_backtest:
    st.subheader("🛠️ Hệ Thống Backtest Dài Hạn (Khung 1DAY)")
    st.caption("Thuật toán Quant: Tự động bắt Râu nến để Stoploss (-7%) hoặc Take Profit (+15%). Chặn bán nếu gãy trend Kumo.")

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        ticker_bt = st.text_input("Nhập mã cổ phiếu để test (Ví dụ: FPT, HPG):", value="FPT", key="bt_ticker").upper()
    with col_input2:
        years_back = st.slider("Số NĂM quá khứ muốn kiểm tra:", min_value=1, max_value=10, value=5)

    if st.button("🚀 Bắt đầu chạy Backtest Tự Động"):
        with st.spinner(f"Đang cào dữ liệu Daily trong {years_back} năm và mô phỏng giao dịch mã {ticker_bt}..."):
            
            # 1. Gọi đúng tên hàm Khung Ngày từ file backtester.py
            df_daily = bt.get_daily_data(ticker_bt, years_back)
            
            if df_daily is not None and not df_daily.empty:
                # 2. Gọi hàm tính toán mây Ichimoku Daily
                df_ichimoku = bt.calculate_ichimoku_daily(df_daily)
                
                if df_ichimoku is not None:
                    # 3. Chạy vòng lặp kiểm thử thông minh bản Daily
                    stats, trade_log = bt.run_ichimoku_backtest_daily(df_ichimoku)
                    
                    st.success(f"Dữ liệu kiểm thử mã {ticker_bt} trong {years_back} năm thành công!")
                    
                    # --- HIỂN THỊ KẾT QUẢ HIỆU SUẤT ---
                    st.subheader("📊 Kết quả hiệu suất chiến lược")
                    m_col1, m_col2, m_col3 = st.columns(3)
                    m_col1.metric("Vốn cuối kỳ", stats["Vốn cuối kỳ"])
                    m_col2.metric("Lợi nhuận ròng", stats["Lợi nhuận ròng"])
                    m_col3.metric("Tỷ lệ Thắng (Win Rate)", stats["Tỷ lệ Thắng (Win Rate)"])
                    
                    # --- HIỂN THỊ NHẬT KÝ CHI TIẾT ---
                    st.subheader("📋 Nhật ký lệnh chi tiết của Bot")
                    st.dataframe(trade_log, use_container_width=True)
                else:
                    st.error("Dữ liệu quá ngắn, không đủ để tính toán đám mây Ichimoku!")
            else:
                st.error("Lỗi: Không lấy được dữ liệu. Hãy kiểm tra lại mã cổ phiếu hoặc API đang bảo trì!")
