# fintrade_ui.py
import streamlit as st
from fintrade_data import load_fintrade_ticker_data, load_fintrade_index_definitions

def render_fintrade_tab(ticker: str):
    st.subheader(f"📊 Dữ liệu FiinTrade — {ticker}")
    
    df = load_fintrade_ticker_data(ticker)
    if df is None:
        st.warning("Không tìm thấy dữ liệu FiinTrade cho mã này.")
        return
    
    # Hiển thị các chỉ số chính
    col1, col2, col3 = st.columns(3)
    # ... điền theo cột thực tế trong file
    
    st.dataframe(df.tail(20))
    
def render_fintrade_methodology():
    """Tab giải thích phương pháp FiinTrade"""
    st.subheader("📖 Phương pháp luận FiinTrade")
    defs = load_fintrade_index_definitions()
    if defs is not None:
        st.dataframe(defs)
