import streamlit as st
import pandas as pd
import concurrent.futures
import streamlit.components.v1 as components #
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
tab_market, tab_screener, tab_simulation, tab_backtest, tab_charts = st.tabs([
    "📊 TỔNG QUAN VN-INDEX", 
    "🚀 BỘ LỌC CỔ PHIẾU", 
    "🔮 MÔ PHỎNG ICHIMOKU",
    "🛠️ BACKTEST KHUNG 1DAY",
    "📈 CHARTS TRADINGVIEW"
    ])
# ==========================================
# TAB 1: THỊ TRƯỜNG CHUNG (TỰ ĐỘNG KHỚP THEO API THỰC TẾ)
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

    intraday_df = get_intraday_vnindex()
    chart_df, df_today = None, None

    if intraday_df is not None and not intraday_df.empty:
        # Đồng bộ hóa tên cột từ API
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
        
        if 'time' in intraday_df.columns and 'volume' in intraday_df.columns and 'close' in intraday_df.columns:
            intraday_df['volume'] = pd.to_numeric(intraday_df['volume'], errors='coerce').fillna(0)
            intraday_df['close'] = pd.to_numeric(intraday_df['close'], errors='coerce').fillna(0)
            intraday_df['time'] = pd.to_datetime(intraday_df['time'])
            intraday_df['date'] = intraday_df['time'].dt.date
            intraday_df['hour_min'] = intraday_df['time'].dt.strftime('%H:%M')
            
            # Lọc khung giờ hành chính chuẩn
            intraday_df = intraday_df[(intraday_df['hour_min'] >= '09:00') & (intraday_df['hour_min'] <= '15:00')]
            
            # 🔑 CHIÊU THỨC: Sắp xếp và lấy ngày tự động theo dữ liệu thực tế cào về
            dates = sorted(intraday_df['date'].unique())
            if len(dates) >= 2:
                today_date = dates[-1]
                yest_date = dates[-2]
                
                df_today = intraday_df[intraday_df['date'] == today_date].copy()
                df_yest = intraday_df[intraday_df['date'] == yest_date].copy()
                
                df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
                df_yest['Vol_Hôm_Qua'] = df_yest['volume'].cumsum()
                
                # Lấy chỉ số chốt dòng dữ liệu thực tế
                current_index = df_today['close'].iloc[-1] if not df_today.empty else 0
                prev_index = df_yest['close'].iloc[-1] if not df_yest.empty else current_index
                index_change = current_index - prev_index
                
                current_vol = df_today['Vol_Hôm_Nay'].iloc[-1] if not df_today.empty else 0
                prev_vol = df_yest['Vol_Hôm_Qua'].iloc[-1] if not df_yest.empty else 0
                vol_change = current_vol - prev_vol
                
                # In ra 3 khối Metric
                m1, m2, m3 = st.columns(3)
                m1.metric("📊 Chỉ số VN-INDEX", f"{current_index:,.2f} đ", f"{index_change:,.2f} đ")
                m2.metric("💰 Thanh khoản Hôm Nay", f"{current_vol:,.0f} CP", f"{vol_change:,.0f} CP" if vol_change != 0 else None)
                m3.metric("⏳ Thanh khoản Hôm Qua (EOD)", f"{prev_vol:,.0f} CP")
                
                # Tạo khung xương thời gian
                times_morning = pd.date_range("09:00", "11:30", freq="min").strftime('%H:%M').tolist()
                times_afternoon = pd.date_range("13:00", "15:00", freq="min").strftime('%H:%M').tolist()
                time_df = pd.DataFrame({'hour_min': times_morning + times_afternoon})
                
                df_yest_agg = df_yest.groupby('hour_min')['Vol_Hôm_Qua'].last().reset_index()
                df_today_agg = df_today.groupby('hour_min')['Vol_Hôm_Nay'].last().reset_index()
                
                chart_df = pd.merge(time_df, df_yest_agg, on='hour_min', how='left')
                chart_df = pd.merge(chart_df, df_today_agg, on='hour_min', how='left')
                
                chart_df['Vol_Hôm_Qua'] = chart_df['Vol_Hôm_Qua'].ffill()
                
                # --- 🔑 TỰ ĐỘNG CHẶT ĐUÔI THEO PHÚT LỚN NHẤT CỦA API THỰC TẾ ---
                if not df_today.empty:
                    max_time_actual = df_today['hour_min'].max()
                    chart_df['Vol_Hôm_Nay'] = chart_df['Vol_Hôm_Nay'].ffill()
                    chart_df.loc[chart_df['hour_min'] > max_time_actual, 'Vol_Hôm_Nay'] = None
                    
                    # Hiện dòng trạng thái báo phút thực tế cho User biết
                    st.info(f"🕒 Tình trạng luồng dữ liệu: API VN-INDEX đang trả số thực tế đến mốc **{max_time_actual}**")
                
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

# ==========================================
# TAB 3: MÔ PHỎNG ICHIMOKU (NÂNG CẤP PLOTLY PRO + VOLUME MA20)
# ==========================================
with tab_simulation:
    st.subheader("🔮 Phòng Thí Nghiệm Chỉ Báo Kỹ Thuật Ichimoku")
    st.caption("Đồ thị chuyên nghiệp: Hỗ trợ kéo chỉnh, phóng to thu nhỏ chuột, tích hợp Volume MA20.")
    
    sim_ticker = st.text_input("Nhập mã cổ phiếu (Gõ xong nhấn Enter):", value="HPG", key="sim_ticker_input").upper().strip()
    
    if sim_ticker:
        with st.spinner(f"Đang dựng đồ thị chuyên nghiệp cho {sim_ticker}..."): 
            df_sim = get_stock_data(sim_ticker)
            
            if df_sim is not None and not df_sim.empty:
                df_sim.columns = [str(c).lower().strip() for c in df_sim.columns]
                
                # 1. Tính toán thông số Ichimoku động từ Sidebar
                df_sim['Tenkan'] = (df_sim['high'].rolling(window=p_tenkan).max() + df_sim['low'].rolling(window=p_tenkan).min()) / 2
                df_sim['Kijun'] = (df_sim['high'].rolling(window=p_kijun).max() + df_sim['low'].rolling(window=p_kijun).min()) / 2
                
                senkou_a_raw = (df_sim['Tenkan'] + df_sim['Kijun']) / 2
                df_sim['Senkou A'] = senkou_a_raw.shift(p_shift)
                
                senkou_b_raw = (df_sim['high'].rolling(window=p_senkou_b).max() + df_sim['low'].rolling(window=p_senkou_b).min()) / 2
                df_sim['Senkou B'] = senkou_b_raw.shift(p_shift)
                
                # --- 📈 TÍNH TOÁN ĐƯỜNG TRUNG BÌNH KHỐI LƯỢNG VOLUME MA20 ---
                df_sim['Vol_MA20'] = df_sim['volume'].rolling(window=20).mean()
                # -------------------------------------------------------------
                
                # Lấy 100 nến gần nhất để biểu đồ cân đối, không bị quá dày
                plot_df = df_sim.tail(100).copy()
                
                if 'time' in plot_df.columns:
                    plot_df['Ngay'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
                    plot_df.set_index('Ngay', inplace=True)
                
                # --- 🚀 BẮT ĐẦU VẼ BIỂU ĐỒ BẰNG PLOTLY ---
                import plotly.graph_objects as go
                from plotly.subplots import make_subplots
                
                # 1. Tạo bộ khung 2 tầng
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.03, 
                                    row_heights=[0.8, 0.2])
                
                # 2. Thêm Nến Nhật (Candlestick)
                fig.add_trace(go.Candlestick(x=plot_df.index,
                                             open=plot_df['open'], high=plot_df['high'],
                                             low=plot_df['low'], close=plot_df['close'],
                                             name='Nến Giá',
                                             increasing_line_color='#00C853', decreasing_line_color='#FF1744'),
                              row=1, col=1)
                
                # 3. Thêm Mây Ichimoku
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Senkou A'], 
                                         line=dict(color='rgba(0, 200, 83, 0.4)', width=1), 
                                         name='Senkou A'), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Senkou B'], 
                                         line=dict(color='rgba(255, 23, 68, 0.4)', width=1),
                                         fill='tonexty', fillcolor='rgba(128, 128, 128, 0.15)', 
                                         name='Mây Kumo'), row=1, col=1)
                
                # 4. Thêm Tenkan 
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Tenkan'], 
                                         line=dict(color='#2962FF', width=1.5), name='Tenkan (9)'), row=1, col=1)
                
                # 5. Thêm Kijun (Đường đậm)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Kijun'], 
                                         line=dict(color='darkred', width=3), name=f'Kijun ({p_kijun})'), row=1, col=1)
                
                # 6. Thêm Volume & MA20
                colors = ['#00C853' if row['close'] >= row['open'] else '#FF1744' for idx, row in plot_df.iterrows()]
                fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['volume'], marker_color=colors, name='Volume'), row=2, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Vol_MA20'], line=dict(color='#FF6D00', width=2, shape='spline'), name='Volume MA20'), row=2, col=1)
                
                # ==============================================================
                # 💎 7. VŨ KHÍ BÍ MẬT: TỰ ĐỘNG BẮN TÍN HIỆU MUA/BÁN LÊN ĐỒ THỊ
                # ==============================================================
                # Logic: MUA khi giá đóng cửa hôm nay vọt lên trên Kijun (hôm qua ở dưới)
                #        BÁN khi giá đóng cửa hôm nay rớt xuống dưới Kijun (hôm qua ở trên)
                plot_df['Prev_Close'] = plot_df['close'].shift(1)
                plot_df['Prev_Kijun'] = plot_df['Kijun'].shift(1)
                
                buy_points = plot_df[(plot_df['Prev_Close'] <= plot_df['Prev_Kijun']) & (plot_df['close'] > plot_df['Kijun'])]
                sell_points = plot_df[(plot_df['Prev_Close'] >= plot_df['Prev_Kijun']) & (plot_df['close'] < plot_df['Kijun'])]
                
                # Vẽ Mũi tên Xanh (MUA) ghim ngay dưới đáy cây nến
                fig.add_trace(go.Scatter(x=buy_points.index, y=buy_points['low'] * 0.98,
                                         mode='markers', marker=dict(symbol='triangle-up', size=14, color='rgba(0, 255, 0, 0.9)', line=dict(width=1, color='darkgreen')),
                                         name='Bắn Tín Hiệu MUA'), row=1, col=1)
                
                # Vẽ Mũi tên Đỏ (BÁN) ghim ngay trên đỉnh cây nến
                fig.add_trace(go.Scatter(x=sell_points.index, y=sell_points['high'] * 1.02,
                                         mode='markers', marker=dict(symbol='triangle-down', size=14, color='rgba(255, 0, 0, 0.9)', line=dict(width=1, color='darkred')),
                                         name='Bắn Tín Hiệu BÁN'), row=1, col=1)
                # ==============================================================

                # 8. Tinh chỉnh Layout tổng thể
                fig.update_layout(
                    title=f"<b>Phân Tích Đa Tầng Chuyên Sâu: {sim_ticker} (Đã bật Mắt Thần)</b>",
                    height=680, 
                    margin=dict(l=10, r=10, t=40, b=10),
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    xaxis_rangeslider_visible=False,
                    dragmode='pan'
                )
                
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                
                # In biểu đồ ra màn hình
                st.plotly_chart(fig, use_container_width=True)
                # ... [Phần code báo lỗi ở dưới giữ nguyên] ...
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
                # ==========================================
# ==========================================
# TAB 5: ĐỒ THỊ TRADINGVIEW TRỰC TIẾP
# ==========================================
import streamlit.components.v1 as components

with tab_charts:
    st.subheader("📊 Hệ Thống Đồ Thị TradingView Trực Tiếp (Bản Free)")
    st.caption("Chart hỗ trợ đầy đủ full tính năng tương tác, lưu cấu hình, vẽ Trendline, Fibonacci và mọi chỉ báo kỹ thuật thị trường.")
    
    # Thiết kế bộ gõ mã khớp sàn để TradingView nhận diện 100% mã Việt Nam
    col_ex, col_tk = st.columns([1, 3])
    with col_ex:
        exchange_tv = st.selectbox("Chọn Sàn:", ["HOSE", "HNX", "UPCOM"], key="tv_tab_exchange_select")
    with col_tk:
        tv_ticker = st.text_input("Nhập mã chứng khoán (Gõ xong nhấn Enter):", value="HPG", key="tv_tab_ticker_input").upper().strip()
    
    if tv_ticker:
        # Định dạng chuẩn quốc tế của TradingView (Ví dụ: HOSE:HPG, HNX:CEO)
        tv_symbol = f"{exchange_tv}:{tv_ticker}"
        
        # 🔑 ĐÃ SỬA: Ép chiều cao cố định 700px và chiều rộng 100%
        tradingview_html = f"""
        <div class="tradingview-widget-container">
          <div id="tradingview_advanced_chart"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget(
          {{
            "width": "100%",
            "height": "700",
            "symbol": "{tv_symbol}",
            "interval": "D",
            "timezone": "Asia/Ho_Chi_Minh",
            "theme": "dark",
            "style": "1",
            "locale": "vi_VN",
            "enable_publishing": false,
            "backgroundColor": "rgba(0, 0, 0, 1)",
            "withdateranges": true,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "details": true,
            "hotlist": true,
            "calendar": false,
            "show_popup_button": true,
            "popup_width": "1000",
            "popup_height": "650",
            "container_id": "tradingview_advanced_chart"
          }}
          );
          </script>
        </div>
        """
        
        # 🔑 ĐÃ SỬA: Đặt khung chứa của Streamlit to hơn 1 chút (720px) để không bị viền cuộn (scrollbar)
        components.html(tradingview_html, height=720)
