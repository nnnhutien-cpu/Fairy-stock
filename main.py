import streamlit as st
import pandas as pd
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
# Nạp các hàm vẽ giao diện từ file riêng biệt
from ui_layout import render_sidebar, render_market_tab, render_screener_results

# Cấu hình trang rộng & Bật sẵn Sidebar
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# 1. Gọi thanh điều khiển Sidebar từ file ui_layout
scan_button, exchange_choice, max_scan = render_sidebar()

# 2. Tiêu đề chính của Web
st.title("📈 Dashboard Phân Tích Dòng Tiền")

# Tạo 2 phân trang (Tabs)
tab_market, tab_screener = st.tabs(["📊 TỔNG QUAN VN-INDEX", "🚀 LỌC SIÊU CỔ PHIẾU"])

# ------------------------------------------
# XỬ LÝ TAB 1: THỊ TRƯỜNG CHUNG
# ------------------------------------------
with tab_market:
    intraday_df = get_intraday_vnindex()
    chart_df, df_today = None, None

    if intraday_df is not None and not intraday_df.empty:
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
            chart_df.set_index('hour_min', inplace=True)
            
    # Đẩy dữ liệu đã tính toán sang file ui_layout để nó tự vẽ đồ thị và khung LED
    render_market_tab(chart_df, df_today)

# ------------------------------------------
# XỬ LÝ TAB 2: BỘ LỌC CỔ PHIẾU DÒNG TIỀN
# ------------------------------------------
with tab_screener:
    st.subheader(f"Kết Quả Lọc Sàn {exchange_choice}")
    
    if scan_button:
        ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
        tickers = get_all_tickers(ex_code)
        tickers_to_scan = tickers[:max_scan]
        
        with st.status(f"Đang phân tích {len(tickers_to_scan)} mã. Cô Tiên đang làm việc...", expanded=True) as status:
            progress_bar = st.progress(0)
            results = []
            total = len(tickers_to_scan)
            
            for i, ticker in enumerate(tickers_to_scan):
                df = get_stock_data(ticker)
                signal_data = calculate_technical_signals(df, ticker)
                
                if signal_data is not None:
                    results.append(signal_data)
                    
                progress_bar.progress((i + 1) / total)
                
            status.update(label=f"✅ Quét xong! Bắt được {len(results)} siêu cổ phiếu.", state="complete", expanded=False)
        
        # Đẩy danh sách siêu cổ phiếu quét được sang file ui_layout để hiển thị bảng dữ liệu
        render_screener_results(results)
    else:
        st.caption("👈 Hãy thiết lập thông số ở thanh công cụ bên trái và bấm 'KÍCH HOẠT LỌC NGAY' để truy tìm siêu cổ phiếu.")
