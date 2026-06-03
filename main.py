import streamlit as st
import pandas as pd
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals

# Cấu hình trang rộng & Bật sẵn Sidebar
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. KHU VỰC SIDEBAR (BẢNG ĐIỀU KHIỂN CHUNG)
# ==========================================
with st.sidebar:
    st.title("🧚‍♀️ CÔ TIÊN STOCK")
    st.caption("Hệ thống phân tích thông minh")
    st.divider()
    
    st.header("⚙️ CẤU HÌNH BỘ LỌC")
    exchange_choice = st.selectbox("Chọn sàn giao dịch:", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
    max_scan = st.slider("Số lượng mã quét tối đa:", 10, 300, 80)
    
    st.divider()
    scan_button = st.button("🚀 KÍCH HOẠT LỌC NGAY", use_container_width=True, type="primary")

# ==========================================
# 2. KHU VỰC MÀN HÌNH CHÍNH (CHIA TABS UI/UX)
# ==========================================
st.title("📈 Dashboard Phân Tích Dòng Tiền")

# Khởi tạo 2 Tabs siêu mượt
tab_market, tab_screener = st.tabs(["📊 TỔNG QUAN VN-INDEX", "🚀 LỌC SIÊU CỔ PHIẾU"])

# ------------------------------------------
# TAB 1: THỊ TRƯỜNG CHUNG (Real-time)
# ------------------------------------------
with tab_market:
    st.subheader("Nhịp Đập Thị Trường (Khung 5 Phút)")
    intraday_df = get_intraday_vnindex()

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
            
            # Đưa các chỉ số lên một khung Container riêng cho nổi bật
            with st.container(border=True):
                col1, col2, col3 = st.columns(3)
                if not df_today.empty:
                    latest_point = df_today.iloc[-1]
                    current_time = latest_point['hour_min']
                    
                    with col1:
                        st.metric(label=f"VN-INDEX ({current_time})", value=f"{latest_point['close']:.2f}")
                    with col2:
                        today_vol_total = latest_point['Vol_Hôm_Nay']
                        st.metric(label="Tổng Khối Lượng Hiện Tại", value=f"{int(today_vol_total):,}")
                    with col3:
                        yest_vol_same_time = chart_df.loc[current_time, 'Vol_Hôm_Qua']
                        if pd.notna(yest_vol_same_time) and yest_vol_same_time > 0:
                            vol_diff_pct = ((today_vol_total - yest_vol_same_time) / yest_vol_same_time) * 100
                            st.metric(label="% Thanh Khoản (So với hôm qua)", 
                                      value=f"{vol_diff_pct:+.2f}%", 
                                      delta=f"{vol_diff_pct:+.2f}%", delta_color="normal")
            
            st.markdown("**📉 Biểu Đồ So Sánh Thanh Khoản (Đỏ: Hôm qua | Xanh: Hôm nay)**")
            st.line_chart(chart_df, color=["#FF0000", "#00FF00"], height=350)
    else:
        st.warning("Đang kết nối dữ liệu VN-INDEX hoặc ngoài giờ giao dịch...")

# ------------------------------------------
# TAB 2: BỘ LỌC CỔ PHIẾU DÒNG TIỀN
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
        
        if results:
            results_df = pd.DataFrame(results)
            st.dataframe(
                results_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Volume Hiện Tại": st.column_config.NumberColumn(format="%d"),
                    "Volume TB 20 Phiên": st.column_config.NumberColumn(format="%d"),
                    "Giá": st.column_config.NumberColumn(format="%.2f")
                }
            )
            st.toast("Phân tích hoàn tất! Chúc Cô Tiên giao dịch thành công 🚀", icon="🧚‍♀️")
        else:
            st.info("Hiện tại không có mã nào vượt qua được bộ lọc khắt khe của bạn.")
    else:
        # Hướng dẫn rỗng cực kỳ tinh tế khi người dùng mới vào Tab này
        st.caption("👈 Hãy thiết lập thông số ở thanh công cụ bên trái và bấm 'KÍCH HOẠT LỌC NGAY' để truy tìm siêu cổ phiếu.")
