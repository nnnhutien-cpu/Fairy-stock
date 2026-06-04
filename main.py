import streamlit as st
from data_loader import get_stock_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export

st.set_page_config(layout="wide")
setup_cache_clear_button()

ex, sig, max_s, p_t, p_k, p_sb, p_s = render_sidebar()

st.title("📈 Fairy Stock Dashboard")

tab1, tab2, tab3 = st.tabs(["📊 Tổng quan", "🚀 Bộ lọc", "🔮 Mô phỏng"])

with tab2:
    if st.button("🚀 Quét dữ liệu"):
        tickers = get_all_tickers(ex)[:max_s]
        results = [calculate_technical_signals(get_stock_data(t), t, p_t, p_k, p_sb, p_s) for t in tickers]
        st.session_state['scan_results'] = [r for r in results if r]
        
    if st.session_state.get('scan_results'):
        df = render_search_and_export(st.session_state['scan_results'])
        render_screener_results(df, sig)
