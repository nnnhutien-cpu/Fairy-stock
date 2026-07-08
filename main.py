import streamlit as st
import pandas as pd
import concurrent.futures
import streamlit.components.v1 as components
from supabase import create_client

from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# --- 1b. GIAO DIỆN: TÍM ĐẬM SANG TRỌNG + FONT + HÒA HEADER ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"], .stMarkdown, .stButton, .stTextInput, .stSelectbox, .stDataFrame {
        font-family: 'Sora', sans-serif !important;
    }

    .stApp {
        background: linear-gradient(180deg, #0f0a1f 0%, #16112e 100%);
        color: #dcd6ec;
    }

    header[data-testid="stHeader"] { background: #0f0a1f !important; }
    header[data-testid="stHeader"] a, header[data-testid="stToolbar"] * { color: #b9aee0 !important; }

    h1 { font-size: 2rem !important; line-height: 1.25 !important; }
    h2, .stSubheader { font-size: 1.4rem !important; }
    h3 { font-size: 1.15rem !important; }
    h1, h2, h3, .stSubheader { color: #a394d4 !important; font-weight: 700 !important; letter-spacing: .2px; }

    section[data-testid="stSidebar"] { background: #120d26; border-right: 1px solid #241a45; }
    section[data-testid="stSidebar"] .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }

    .block-container {
        padding-top: 2.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
        max-width: 100% !important;
    }

    div[data-testid="stMetric"] {
        background: #1a1436;
        border: 1px solid #2c2151;
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 4px 14px rgba(40,25,80,.35);
    }
    div[data-testid="stMetricValue"] { color: #f2eeff; font-weight: 700; font-size: 1.5rem !important; }
    div[data-testid="stMetricLabel"] { color: #a99fcf; font-size: .85rem !important; }

    .stButton > button {
        border-radius: 10px; font-weight: 600; border: 1px solid #4a3a7a; transition: all .15s ease;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #4c1d95, #6d28d9); color: #efe9ff; border: none;
    }
    .stButton > button:hover { transform: translateY(-1px); filter: brightness(1.12); }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: #120d26; padding: 6px; border-radius: 12px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 6px 14px; color: #a99fcf; font-weight: 600; font-size: .9rem; }
    .stTabs [aria-selected="true"] { background: linear-gradient(90deg, #4c1d95, #6d28d9) !important; color: #ffffff !important; }

    [data-testid="stAppDeployButton"] button, .stDeployButton button, button[title="Manage app"] {
        background: linear-gradient(90deg, #4c1d95, #6d28d9) !important; color: #efe9ff !important;
        border: none !important; border-radius: 8px !important; font-weight: 600 !important;
    }
    #MainMenu button, [data-testid="stMainMenu"] button { color: #b9aee0 !important; }
    #MainMenu button:hover { background: #2c2151 !important; }
    [data-testid="stSidebarCollapseButton"] button, [data-testid="collapsedControl"] button {
        color: #b9aee0 !important; background: #1a1436 !important; border-radius: 8px !important;
    }
    [data-testid="StyledFullScreenButton"] { color: #b9aee0 !important; }
    .stSlider [role="slider"] { background: #6d28d9 !important; }

    .stTextInput input, .stSelectbox div[data-baseweb="select"] { background: #1a1436; color: #dcd6ec; border-radius: 8px; }
    .stDataFrame { border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI SUPABASE (an toàn: thiếu secrets vẫn không làm sập app) ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_connection()

# --- Danh sách mã bị đình chỉ / hạn chế giao dịch (tự bổ sung khi phát hiện) ---
BLACKLIST = {"BCG", "HBC", "HNG", "POM", "HAG", "ITA", "TGG", "TTB"}

# --- 3. KHỞI TẠO BIẾN CHO GIAO DIỆN ---
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()

setup_cache_clear_button()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật")

# --- 4. TẠO 5 TAB ---
tab_market, tab_screener, tab_simulation, tab_backtest, tab_reports = st.tabs([
    "🌟 Thị Trường", "🔍 Bộ Lọc", "🔮 Mô Phỏng", "🛠️ Backtest", "📑 Báo Cáo"
])

# ==========================================
# TAB 1: THỊ TRƯỜNG CHUNG
# ==========================================
with tab_market:
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

            intraday_df = intraday_df[(intraday_df['hour_min'] >= '09:00') & (intraday_df['hour_min'] <= '15:00')]

            dates = sorted(intraday_df['date'].unique())
            if len(dates) >= 2:
                today_date = dates[-1]
                yest_date = dates[-2]

                df_today = intraday_df[intraday_df['date'] == today_date].copy()
                df_yest = intraday_df[intraday_df['date'] == yest_date].copy()

                df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
                df_yest['Vol_Hôm_Qua'] = df_yest['volume'].cumsum()

                current_index = df_today['close'].iloc[-1] if not df_today.empty else 0
                prev_index = df_yest['close'].iloc[-1] if not df_yest.empty else current_index
                index_change = current_index - prev_index

                current_vol = df_today['Vol_Hôm_Nay'].iloc[-1] if not df_today.empty else 0
                prev_vol = df_yest['Vol_Hôm_Qua'].iloc[-1] if not df_yest.empty else 0
                vol_change = current_vol - prev_vol

                m1, m2, m3 = st.columns(3)
                m1.metric("📊 Chỉ số VN-INDEX", f"{current_index:,.2f} đ", f"{index_change:,.2f} đ")
                m2.metric("💰 Thanh khoản Hôm Nay", f"{current_vol:,.0f} CP", f"{vol_change:,.0f} CP" if vol_change != 0 else None)
                m3.metric("⏳ Thanh khoản Hôm Qua (EOD)", f"{prev_vol:,.0f} CP")

                times_morning = pd.date_range("09:00", "11:30", freq="min").strftime('%H:%M').tolist()
                times_afternoon = pd.date_range("13:00", "15:00", freq="min").strftime('%H:%M').tolist()
                time_df = pd.DataFrame({'hour_min': times_morning + times_afternoon})

                df_yest_agg = df_yest.groupby('hour_min')['Vol_Hôm_Qua'].last().reset_index()
                df_today_agg = df_today.groupby('hour_min')['Vol_Hôm_Nay'].last().reset_index()

                chart_df = pd.merge(time_df, df_yest_agg, on='hour_min', how='left')
                chart_df = pd.merge(chart_df, df_today_agg, on='hour_min', how='left')

                chart_df['Vol_Hôm_Qua'] = chart_df['Vol_Hôm_Qua'].ffill()

                if not df_today.empty:
                    max_time_actual = df_today['hour_min'].max()
                    chart_df['Vol_Hôm_Nay'] = chart_df['Vol_Hôm_Nay'].ffill()
                    chart_df.loc[chart_df['hour_min'] > max_time_actual, 'Vol_Hôm_Nay'] = None
                    st.info(f"🕒 Tình trạng luồng dữ liệu: API VN-INDEX đang trả số thực tế đến mốc **{max_time_actual}**")

                chart_df.set_index('hour_min', inplace=True)
    else:
        st.warning("⚠️ Đang chờ dữ liệu VN-INDEX từ API. Vui lòng tải lại trang sau ít phút...")

    render_market_tab(chart_df, df_today)

# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU
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

            with st.status(f"Đang dùng 15 Luồng an toàn quét {len(tickers_to_scan)} mã (Dữ liệu Daily 365 ngày)...", expanded=True) as status:
                progress_bar = st.progress(0)
                results = []
                total = len(tickers_to_scan)
                processed = 0

                def process_ticker(ticker):
                    # Lớp 1: chặn mã đã biết bị đình chỉ / hạn chế GD
                    if ticker in BLACKLIST:
                        return None

                    df = get_stock_data(ticker, days_back=365)
                    if df is None or df.empty:
                        return None

                    # Lớp 2: VƯỢT BẪY DỮ LIỆU CŨ — loại mã không có phiên mới trong 7 ngày
                    # (mã đình chỉ / hủy niêm yết / ngừng GD sẽ có phiên cuối cách xa hôm nay)
                    try:
                        last_date = pd.to_datetime(df['time']).max().normalize()
                        days_stale = (pd.Timestamp.now().normalize() - last_date).days
                        if days_stale > 7:
                            return None
                    except Exception:
                        return None

                    return calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)

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
                        progress_bar.progress(processed / total)

                status.update(label=f"✅ Đã quét xong {len(results)} mã hợp lệ (đã loại mã đình chỉ / dữ liệu cũ)!", state="complete", expanded=False)
            st.session_state['scan_results'] = results

    if st.session_state['scan_results']:
        st.divider()
        raw_df = pd.DataFrame(st.session_state['scan_results'])
        df_display = render_search_and_export(raw_df)
        render_screener_results(df_display, signal_filter)
    else:
        st.caption("Hãy cấu hình thông số ở Sidebar trái và bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' để bắt đầu.")

# ==========================================
# TAB 3: MÔ PHỎNG ICHIMOKU
# ==========================================
with tab_simulation:
    st.subheader("🔮 Mô Phỏng Ichimoku & Volume")
    st.caption("Giao diện tối giản: Chỉ hiển thị Đường Giá (Line), Ichimoku và Volume MA20.")

    sim_ticker = st.text_input("Nhập mã cổ phiếu (Gõ xong nhấn Enter):", value="HPG", key="sim_ticker_input").upper().strip()

    if sim_ticker:
        with st.spinner(f"Đang xử lý dữ liệu {sim_ticker}..."):
            df_sim = get_stock_data(sim_ticker)

            if df_sim is not None and not df_sim.empty:
                df_sim.columns = [str(c).lower().strip() for c in df_sim.columns]

                df_sim['Tenkan'] = (df_sim['high'].rolling(window=p_tenkan).max() + df_sim['low'].rolling(window=p_tenkan).min()) / 2
                df_sim['Kijun'] = (df_sim['high'].rolling(window=p_kijun).max() + df_sim['low'].rolling(window=p_kijun).min()) / 2

                senkou_a_raw = (df_sim['Tenkan'] + df_sim['Kijun']) / 2
                df_sim['Senkou A'] = senkou_a_raw.shift(p_shift)

                senkou_b_raw = (df_sim['high'].rolling(window=p_senkou_b).max() + df_sim['low'].rolling(window=p_senkou_b).min()) / 2
                df_sim['Senkou B'] = senkou_b_raw.shift(p_shift)

                df_sim['Vol_MA20'] = df_sim['volume'].rolling(window=20).mean()

                plot_df = df_sim.tail(100).copy()

                if 'time' in plot_df.columns:
                    plot_df['Ngay'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
                    plot_df.set_index('Ngay', inplace=True)

                import plotly.graph_objects as go
                from plotly.subplots import make_subplots

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                    vertical_spacing=0.03, row_heights=[0.8, 0.2])

                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['close'],
                                         line=dict(color='#c4b5fd', width=2), name='Giá Đóng Cửa'), row=1, col=1)

                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Senkou A'],
                                         line=dict(color='rgba(0, 200, 83, 0.4)', width=1), name='Senkou A'), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Senkou B'],
                                         line=dict(color='rgba(255, 23, 68, 0.4)', width=1),
                                         fill='tonexty', fillcolor='rgba(128, 128, 128, 0.15)', name='Mây Kumo'), row=1, col=1)

                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Tenkan'], line=dict(color='#2962FF', width=1.5), name=f'Tenkan ({p_tenkan})'), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Kijun'], line=dict(color='darkred', width=3), name=f'Kijun ({p_kijun})'), row=1, col=1)

                colors = ['#00C853' if row['close'] >= row['open'] else '#FF1744' for idx, row in plot_df.iterrows()]
                fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['volume'], marker_color=colors, name='Volume'), row=2, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Vol_MA20'], line=dict(color='#FF6D00', width=2, shape='spline'), name='Volume MA20'), row=2, col=1)

                plot_df['Prev_Close'] = plot_df['close'].shift(1)
                plot_df['Prev_Kijun'] = plot_df['Kijun'].shift(1)
                buy_points = plot_df[(plot_df['Prev_Close'] <= plot_df['Prev_Kijun']) & (plot_df['close'] > plot_df['Kijun'])]
                sell_points = plot_df[(plot_df['Prev_Close'] >= plot_df['Prev_Kijun']) & (plot_df['close'] < plot_df['Kijun'])]

                fig.add_trace(go.Scatter(x=buy_points.index, y=buy_points['close'] * 0.98,
                                         mode='markers', marker=dict(symbol='triangle-up', size=14, color='lime'), name='Tín Hiệu MUA'), row=1, col=1)
                fig.add_trace(go.Scatter(x=sell_points.index, y=sell_points['close'] * 1.02,
                                         mode='markers', marker=dict(symbol='triangle-down', size=14, color='red'), name='Tín Hiệu BÁN'), row=1, col=1)

                fig.update_layout(
                    title=f"<b>Phân Tích Ichimoku (Line Chart): {sim_ticker}</b>",
                    height=680, margin=dict(l=10, r=10, t=40, b=10),
                    showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    xaxis_rangeslider_visible=False, dragmode='pan',
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#dcd6ec')
                )
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"⚠️ Không có dữ liệu cho mã {sim_ticker}. Hãy kiểm tra lại mã cổ phiếu!")

# ==========================================
# TAB 4: HỆ THỐNG BACKTEST
# ==========================================
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
            df_daily = bt.get_daily_data(ticker_bt, years_back)

            if df_daily is not None and not df_daily.empty:
                df_ichimoku = bt.calculate_ichimoku_daily(df_daily)

                if df_ichimoku is not None:
                    stats, trade_log = bt.run_ichimoku_backtest_daily(df_ichimoku)

                    st.success(f"Dữ liệu kiểm thử mã {ticker_bt} trong {years_back} năm thành công!")

                    st.subheader("📊 Kết quả hiệu suất chiến lược")
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

# ==========================================
# TAB 5: BÁO CÁO PHÂN TÍCH TỪ CTCK
# ==========================================
with tab_reports:
    st.subheader("📑 Hệ Thống Phân Tích Định Giá Cổ Phiếu")

    if supabase is None:
        st.warning("⚠️ Chưa cấu hình SUPABASE_URL / SUPABASE_KEY trong Secrets. Tab Báo Cáo tạm thời chưa dùng được.")
        st.stop()

    st.caption("Dữ liệu hệ thống tự động quét hàng ngày từ 15+ CTCK hàng đầu (SSI, VND, VCI, MBS, MAS, KIS, VCBS, KB, CTS, BSI...).")

    col1, col2 = st.columns([1, 3])
    with col1:
        filter_action = st.selectbox("Lọc Khuyến Nghị:", ["Tất cả", "MUA", "NẮM GIỮ", "BÁN"])
    with col2:
        rep_ticker = st.text_input("Nhập mã cổ phiếu (Ví dụ: FPT, HPG) hoặc để trống để xem toàn thị trường:", value="", key="rep_ticker_db").upper().strip()

    with st.spinner("Đang truy vấn kho dữ liệu định giá..."):
        try:
            query = supabase.table("analyst_reports").select("*")

            if rep_ticker:
                query = query.eq("ticker", rep_ticker)

            response = query.execute()
            df_reports = pd.DataFrame(response.data)

            if not df_reports.empty:
                if filter_action != "Tất cả":
                    df_reports = df_reports[df_reports['action'] == filter_action]

                if not df_reports.empty:
                    df_reports['target_price'] = pd.to_numeric(df_reports['target_price'], errors='coerce')
                    df_reports['buy_price'] = pd.to_numeric(df_reports['buy_price'], errors='coerce')

                    df_reports['Kỳ Vọng (%)'] = ((df_reports['target_price'] - df_reports['buy_price']) / df_reports['buy_price'] * 100).round(2)

                    df_reports = df_reports.sort_values(by='date', ascending=False)
                    df_display = df_reports[['date', 'ticker', 'company', 'action', 'buy_price', 'target_price', 'Kỳ Vọng (%)', 'report_url']].copy()

                    st.dataf
