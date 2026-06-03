import streamlit as st
from vnstock import stock_historical_data
import pandas as pd

# Cấu hình trang web
st.set_page_config(page_title="Cổ Tiên Stock Dashboard", layout="wide")
st.title("📈 Dashboard Phân Tích Cổ Phiếu - Cổ Tiên Stock")

# Thanh nhập liệu mã cổ phiếu
symbol = st.text_input("Nhập mã cổ phiếu (Ví dụ: HPG, SSI, FPT):", "HPG").upper()

if st.button("Lấy dữ liệu"):
    try:
        with st.spinner('Đang tải dữ liệu từ Vnstock...'):
            # Gọi hàm cào dữ liệu từ vnstock
            df = stock_historical_data(symbol=symbol, 
                                       start_date="2023-01-01", 
                                       end_date="2024-06-01", 
                                       resolution="1D", type="stock")
            
            st.success(f"Đã cào thành công dữ liệu mã {symbol}")
            
            # Vẽ biểu đồ giá đóng cửa
            st.subheader(f"Biểu Đồ Giá Đóng Cửa - {symbol}")
            # Đặt cột 'time' làm trục X để biểu đồ hiển thị đúng ngày tháng
            chart_data = df.set_index('time')['close']
            st.line_chart(chart_data)
            
            # Hiển thị bảng số liệu chi tiết
            st.subheader("Bảng Số Liệu Chi Tiết")
            st.dataframe(df, use_container_width=True)
            
    except Exception as e:
        st.error(f"Lỗi: Không thể lấy dữ liệu mã {symbol}. Vui lòng kiểm tra lại.")
