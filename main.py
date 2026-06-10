import streamlit as st
import pandas as pd
import concurrent.futures
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export # Gọi file UX
import backtester as bt # [MỚI] Nhập file backtest khung 3 phút

st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

# Đọc các thông số Ichimoku động từ Sidebar bên trái
exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()

# [GỌI HÀM UX] Tạo nút xóa Cache
setup_cache_clear_button()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật")

# [CẬP NHẬT] Thêm Tab thứ 4 cho Backtest
tab_market, tab_screener, tab_simulation, tab_backtest = st.tabs([
    "📊 TỔNG QUAN VN-INDEX", 
    "🚀 BỘ LỌC CỔ PHIẾU", 
    "🔮 MÔ PHỎNG ICHIMOKU",
    "🛠️ BACKTEST KHUNG 3P"
])

with tab_market:
    intraday_df = get_intraday_vnindex()
    chart_df, df_today = None, None

    # Bẫy lỗi: Đảm bảo có dữ liệu mới vẽ biểu đồ để không bị trắng bảng
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

with tab_screener:
    st.subheader(f"Danh Sách Quét Sàn {exchange_choice} (>20 Tỷ VNĐ)")
    scan_button = st.button("🚀 KÍCH HOẠT QUÉT TOÀN DIỆN", use_container_width=True, type="primary")
    
    if scan_button:
        ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
        tickers = get_all_tickers(ex_code)
        
        # Bẫy lỗi không lấy được danh sách mã
        if tickers is None or len(tickers) == 0:
            st.error("⚠️ Lỗi mạng: Không lấy được danh sách mã chứng khoán!")
        else:
            tickers_to_scan = tickers[:max_scan]
            
            with st.status(f"Đang dùng 20 Luồng quét {len(tickers_to_scan)} mã. Tốc độ siêu tốc...", expanded=True) as status:
                progress_bar = st.progress(0)
                results = []
                total = len(tickers_to_scan)
                processed = 0

                def process_ticker(ticker):
                    df = get_stock_data(ticker)
                    if df is None or df.empty:
                        return None
                    signal_data = calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
                    return signal_data

                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}
                    for future in concurrent.futures.as_completed(future_to_ticker):
                        processed += 1
                        try:
                            res = future.result()
                            if res is not None:
                                results.append(res)
                        except Exception:
                            pass
                        progress_bar.progress(processed / total)
                
                status.update(label=f"✅ Đã quét xong siêu tốc!", state="complete", expanded=False)
            st.session_state['scan_results'] = results
    
    if st.session_state['scan_results']:
        st.divider()
        
        # [SỬA LỖI TẠI ĐÂY] Ép danh sách (List) biến thành Bảng Pandas (DataFrame) trước
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

# [MỚI] Tích hợp Tab 4: Backtest Cổ Phiếu Khung 3 Phút
with tab_backtest:
    st.subheader("🛠️ Hệ Thống Kiểm Thử Chiến Lược Mây Ichimoku Khung 3 Phút")
    st.caption("Hệ thống tự động gộp nến 1 phút thành 3 phút, giả lập mua khi giá vượt Mây và bán khi gãy Mây.")

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        ticker_bt = st.text_input("Nhập mã cổ phiếu để test (Ví dụ: VGI, SSI):", value="VGI", key="bt_ticker").upper()
    with col_input2:
        days_back = st.slider("Số ngày quá khứ muốn kiểm tra:", min_value=5, max_value=60, value=30)

    if st.button("🚀 Bắt đầu chạy Backtest"):
        with st.spinner(f"Đang cào dữ liệu 1 phút và gộp nến 3 phút mô phỏng mã {ticker_bt}..."):
            # Gọi hàm cào dữ liệu 3 phút từ file backtester.py
            df_3m = bt.get_3m_data(ticker_bt, days_back)
            
            if df_3m is not None and not df_3m.empty:
                df_ichimoku = bt.calculate_ichimoku_3m(df_3m)
                if df_ichimoku is not None:
                    stats, trade_log = bt.run_ichimoku_backtest(df_ichimoku)
                    
                    st.success(f"Dữ liệu kiểm thử mã {ticker_bt} thành công!")
                    
                    st.subheader("📊 Kết quả hiệu suất chỉ báo")
                    m_col1, m_col2, m_col3 = st.columns(3)
                    m_col1.metric("Vốn cuối kỳ", stats["Vốn cuối kỳ"])
                    m_col2.metric("Lợi nhuận ròng", stats["Lợi nhuận ròng"])
                    m_col3.metric("Tỷ lệ Thắng (Win Rate)", stats["Tỷ lệ Thắng (Win Rate)"])
                    
                    st.subheader("📋 Nhật ký lệnh chi tiết của Bot")
                    st.dataframe(trade_log, use_container_width=True)
                else:
                    st.error("Dữ liệu quá ngắn, không đủ để tính toán đám mây Ichimoku!")
            else:
                st.error("Lỗi: Không lấy được dữ liệu. Hãy kiểm tra lại mã cổ phiếu hoặc API đang bảo trì!")
