import streamlit as st
import pandas as pd
import concurrent.futures
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from valuation import get_stock_valuation # [MỚI] Gọi file định giá

st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Định Giá")

tab_market, tab_screener = st.tabs(["📊 TỔNG QUAN VN-INDEX", "🚀 BỘ LỌC SIÊU CỔ PHIẾU"])

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
            
    render_market_tab(chart_df, df_today)

with tab_screener:
    st.subheader(f"Danh Sách Quét Sàn {exchange_choice} (>20 Tỷ VNĐ)")
    scan_button = st.button("🚀 KÍCH HOẠT QUÉT TOÀN DIỆN", use_container_width=True, type="primary")
    
    if scan_button:
        ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
        tickers = get_all_tickers(ex_code)
        tickers_to_scan = tickers[:max_scan]
        
        with st.status(f"Đang dùng 10 Luồng quét {len(tickers_to_scan)} mã. Đang lấy Vốn hóa lưu hành...", expanded=True) as status:
            progress_bar = st.progress(0)
            results = []
            total = len(tickers_to_scan)
            processed = 0

            def process_ticker(ticker):
                # 1. Cào giá
                df = get_stock_data(ticker)
                # 2. Tính toán kỹ thuật
                signal_data = calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
                
                # 3. [MỚI] Nếu vượt qua bộ lọc 20 Tỷ, thì đi cào thêm Định giá P/E, P/B
                if signal_data is not None:
                    val_data = get_stock_valuation(ticker, signal_data["Ichimoku_Cloud"])
                    signal_data.update(val_data) # Gộp kết quả
                    return signal_data
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}
                for future in concurrent.futures.as_completed(future_to_ticker):
                    processed += 1
                    try:
                        res = future.result()
                        if res is not None:
                            results.append(res)
                    except Exception as e:
                        pass
                    progress_bar.progress(processed / total)
                
            status.update(label=f"✅ Đã quét xong siêu tốc! Hiển thị dữ liệu nhóm: {signal_filter}", state="complete", expanded=False)
        
        st.session_state['scan_results'] = results
    
    if st.session_state['scan_results']:
        render_screener_results(st.session_state['scan_results'], signal_filter)
    else:
        st.caption(f"Hãy cấu hình thông số ở Sidebar trái và bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' để bắt đầu.")
