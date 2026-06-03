import streamlit as st
import pandas as pd
from data_loader import get_stock_data, get_vnindex_data
from indicators import calculate_technical_signals

# Cấu hình trang rộng
st.set_page_config(page_title="Cô Tiên Stock", layout="wide")
st.title("🧚‍♀️ Hệ Thống Phân Tích - Cô Tiên Stock")

# --- PHẦN 1: THỐNG KÊ VN-INDEX ---
st.header("1. Thị Trường Chung (VN-INDEX)")
vnindex_df = get_vnindex_data()

if vnindex_df is not None and len(vnindex_df) >= 2:
    # Lấy dữ liệu 2 ngày gần nhất
    today_data = vnindex_df.iloc[-1]
    yesterday_data = vnindex_df.iloc[-2]
    
    # Tính toán chênh lệch
    price_diff = today_data['close'] - yesterday_data['close']
    vol_diff = today_data['volume'] - yesterday_data['volume']
    
    # Hiển thị bằng Widget Metric của Streamlit
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label=f"Điểm VN-INDEX ({today_data['time']})", 
                  value=today_data['close'], 
                  delta=f"{round(price_diff, 2)} điểm")
    with col2:
        st.metric(label="Thanh Khoản (Volume)", 
                  value=f"{int(today_data['volume']):,}", 
                  delta=f"{int(vol_diff):,} cổ phiếu")
else:
    st.warning("Đang tải dữ liệu VN-INDEX hoặc ngoài giờ giao dịch...")

st.divider() # Đường kẻ ngang

# --- PHẦN 2: LỌC TÍN HIỆU CỔ PHIẾU ---
st.header("2. Lọc Tín Hiệu Kỹ Thuật (Screener)")
st.write("Đang quét dữ liệu kỹ thuật mới nhất. Chờ một chút nhé...")

# Danh sách mã bạn muốn theo dõi (Bạn có thể thêm bớt tùy ý)
watch_list = ["HPG", "SSI", "FPT", "VND", "TCB", "MBB"]

if st.button("Cập nhật tín hiệu ngay"):
    with st.spinner("Cô Tiên đang quét bảng điện..."):
        results = []
        for ticker in watch_list:
            df = get_stock_data(ticker)
            signal_data = calculate_technical_signals(df, ticker)
            if signal_data:
                results.append(signal_data)
        
        if results:
            # Biến List thành Bảng DataFrame để hiển thị cho đẹp
            results_df = pd.DataFrame(results)
            
            # Đặt Ticker làm cột đầu tiên
            st.dataframe(results_df, use_container_width=True, hide_index=True)
            st.success("Đã phân tích xong!")
        else:
            st.error("Không lấy được dữ liệu, vui lòng thử lại sau.")
