import streamlit as st
import pandas as pd
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals

# Cấu hình trang rộng & Bật sẵn Sidebar
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. KHU VỰC SIDEBAR (UI/UX BẢNG ĐIỀU KHIỂN)
# ==========================================
with st.sidebar:
    st.title("🧚‍♀️ CÔ TIÊN STOCK")
    st.caption("Hệ thống lọc dòng tiền thông minh")
    st.divider()
    
    st.header("⚙️ BỘ LỌC CỔ PHIẾU")
    exchange_choice = st.selectbox("Chọn sàn giao dịch:", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
    max_scan = st.slider("Số lượng mã quét tối đa:", 10, 300, 80)
    
    st.divider()
    # Nút bấm được làm nổi bật (type="primary") và mở rộng đầy thanh bên
    scan_button = st.button("🚀 KÍCH HOẠT LỌC NGAY", use_container_width=True, type="primary")

# ==========================================
# 2. KHU VỰC MÀN HÌNH CHÍNH (MAIN VIEW)
# ==========================================
st.title("📈 Dashboard Phân Tích Dòng Tiền")

# --- PHẦN 1: THỐNG KÊ VN-INDEX ---
st.header("1. Thị Trường Chung (VN-INDEX Real-time)")
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
        
        col1, col2 = st.columns([1, 2])
        with col1:
            if not df_today.empty:
                latest_point = df_today.iloc[-1]
                st.metric(label=f"VN-INDEX ({latest_point['hour_min']})", 
                          value=f"{latest_point['close']:.2f}")
                
                current_time = latest_point['hour_min']
                yest_vol_same_time = chart_df.loc[current_time, 'Vol_Hôm_Qua']
                today_vol_total = latest_point['Vol_Hôm_Nay']
                
                if pd.notna(yest_vol_same_time) and yest_vol_same_time > 0:
                    vol_diff_pct = ((today_vol_total - yest_vol_same_time) / yest_vol_same_time) * 100
                    st.metric(label="Tốc độ Thanh khoản", 
                              value=f"{int(today_vol_total):,}", 
                              delta=f"{vol_diff_pct:+.2f}% so với hôm qua")
        with col2:
            st.markdown("**📈 Biểu Đồ Thanh Khoản Cộng Dồn Trong Phiên**")
            st.line_chart(chart_df, color=["#FF0000", "#00FF00"])
else:
    st.warning("Đang kết nối dữ liệu VN-INDEX hoặc ngoài giờ giao dịch...")

st.divider()

# --- PHẦN 2: HIỂN THỊ KẾT QUẢ LỌC ---
st.header("2. Siêu Cổ Phiếu Dòng Tiền (>20 Tỷ)")

# Chỉ chạy vòng lặp cào dữ liệu khi nút bên Sidebar được bấm
if scan_button:
    ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
    tickers = get_all_tickers(ex_code)
    tickers_to_scan = tickers[:max_scan]
    
    # UI mượt mà: Dùng st.status thay vì text nhảy lộn xộn
    with st.status(f"Đang phân tích {len(tickers_to_scan)} mã sàn {exchange_choice}...", expanded=True) as status:
        progress_bar = st.progress(0)
        results = []
        total = len(tickers_to_scan)
        
        for i, ticker in enumerate(tickers_to_scan):
            df = get_stock_data(ticker)
            signal_data = calculate_technical_signals(df, ticker)
            
            if signal_data is not None:
                results.append(signal_data)
                
            progress_bar.progress((i + 1) / total)
            
        # Thu gọn thanh trạng thái khi quét xong cho gọn màn hình
        status.update(label=f"✅ Hoàn tất! Tìm thấy {len(results)} mã.", state="complete", expanded=False)
    
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
        # Hiển thị thông báo pop-up nhẹ nhàng thay vì bóng bay chiếm diện tích
        st.toast("Phân tích hoàn tất! Chúc Cô Tiên giao dịch thành công 🚀", icon="🧚‍♀️")
    else:
        st.warning("Hiện tại không có mã nào đạt đủ tiêu chí dòng tiền trên 20 tỷ và tín hiệu kỹ thuật.")
else:
    # Màn hình chờ khi chưa bấm nút
    st.info("👈 Hãy chọn cấu hình ở thanh điều khiển bên trái và bấm nút 'KÍCH HOẠT LỌC NGAY' để bắt đầu.")
