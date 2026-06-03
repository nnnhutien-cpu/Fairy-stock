import streamlit as st
import pandas as pd
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers
from indicators import calculate_technical_signals

# Cấu hình trang rộng
st.set_page_config(page_title="Cô Tiên Stock", layout="wide")
st.title("🧚‍♀️ Hệ Thống Phân Tích - Cô Tiên Stock")

# --- PHẦN 1: THỐNG KÊ VN-INDEX (THANH KHOẢN REALTIME) ---
st.header("1. Thị Trường Chung (VN-INDEX)")
vnindex_df = get_vnindex_data()

if vnindex_df is not None and len(vnindex_df) >= 2:
    today_data = vnindex_df.iloc[-1]
    yesterday_data = vnindex_df.iloc[-2]
    
    # Tính toán chênh lệch điểm số và khối lượng
    price_diff = today_data['close'] - yesterday_data['close']
    vol_diff = today_data['volume'] - yesterday_data['volume']
    
    # Tính % tăng/giảm thanh khoản hôm nay so với hôm qua
    vol_pct_change = (vol_diff / yesterday_data['volume']) * 100
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label=f"Điểm VN-INDEX ({today_data['time']})", 
                  value=f"{today_data['close']:.2f}", 
                  delta=f"{price_diff:.2f} điểm")
    with col2:
        # Hiển thị khối lượng kèm theo mức % tăng giảm so với hôm qua cực trực quan
        st.metric(label="Thanh Khoản Real-time (So với hôm qua)", 
                  value=f"{int(today_data['volume']):,}", 
                  delta=f"{int(vol_diff):+,} ({vol_pct_change:+.2f}%)")
else:
    st.warning("Đang kết nối dữ liệu VN-INDEX hoặc thị trường chưa mở cửa...")

st.divider()

# --- PHẦN 2: BỘ LỌC SIÊU CỔ PHIẾU ---
st.header("2. Lọc Cổ Phiếu Theo Dòng Tiền & Kỹ Thuật (>20 Tỷ)")

col1, col2 = st.columns(2)
with col1:
    exchange_choice = st.selectbox("Chọn sàn giao dịch:", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
with col2:
    max_scan = st.slider("Giới hạn số mã quét để tránh quá tải", 10, 300, 80)

if st.button("🚀 Kích hoạt Siêu Lọc"):
    ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
    
    tickers = get_all_tickers(ex_code)
    tickers_to_scan = tickers[:max_scan]
    
    st.write(f"Đang quét dữ liệu kỹ thuật và thanh khoản của {len(tickers_to_scan)} mã sàn {exchange_choice}...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    total = len(tickers_to_scan)
    
    for i, ticker in enumerate(tickers_to_scan):
        status_text.text(f"Đang cào & phân tích mã: {ticker} ({i+1}/{total})")
        
        df = get_stock_data(ticker)
        signal_data = calculate_technical_signals(df, ticker)
        
        if signal_data is not None:
            results.append(signal_data)
            
        progress_bar.progress((i + 1) / total)
        
    status_text.text(f"✅ Hoàn tất! Tìm thấy {len(results)} cổ phiếu thỏa mãn tiêu chí.")
    
    if results:
        results_df = pd.DataFrame(results)
        
        # Định dạng hiển thị số cho đẹp mắt (thêm dấu phẩy hàng nghìn cho 2 cột Volume)
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
        st.balloons()
    else:
        st.warning("Hiện tại không có mã nào đạt đủ cả 2 tiêu chí dòng tiền trên 20 tỷ và tín hiệu kỹ thuật tích cực.")
