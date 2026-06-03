import streamlit as st

def draw_closing_price_chart(df, symbol):
    """Hàm này chuyên vẽ biểu đồ đường cho giá đóng cửa"""
    st.subheader(f"Biểu Đồ Giá Đóng Cửa - {symbol}")
    # Thiết lập cột 'time' làm trục X
    chart_data = df.set_index('time')['close']
    st.line_chart(chart_data)
