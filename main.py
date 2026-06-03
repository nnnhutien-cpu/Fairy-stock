import streamlit as st
# Nhúng 2 file vệ tinh mà bạn vừa tạo vào hệ thống
from data_loader import get_stock_data
from charts import draw_closing_price_chart

# Cấu hình giao diện tổng
st.set_page_config(page_title="Cổ Tiên Stock Dashboard", layout="wide")
st.title("📈 Dashboard Phân Tích Cổ Phiếu - Cổ Tiên Stock")

# Nhập mã cổ phiếu
symbol = st.text_input("Nhập mã cổ phiếu (Ví dụ: HPG, SSI, FPT):", "HPG").upper()

if st.button("Lấy dữ liệu"):
    with st.spinner('Đang tải dữ liệu từ Vnstock...'):
        
        # 1. Gọi file data_loader đi lấy dữ liệu
        df = get_stock_data(symbol, "2023-01-01", "2024-06-01")
        
        if df is not None:
            st.success(f"Đã cào thành công dữ liệu mã {symbol}")
            
            # 2. Gọi file charts ra vẽ biểu đồ
            draw_closing_price_chart(df, symbol)
            
            # 3. Hiển thị bảng số liệu
            st.subheader("Bảng Số Liệu Chi Tiết")
            st.dataframe(df, use_container_width=True)
        else:
            st.error(f"Lỗi: Không thể lấy dữ liệu mã {symbol}. Vui lòng kiểm tra lại.")
