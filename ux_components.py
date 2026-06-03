import streamlit as st
import pandas as pd

def setup_cache_clear_button():
    with st.sidebar:
        if st.button("🔄 Xóa bộ nhớ đệm"):
            st.cache_data.clear()
            st.rerun()

def render_search_and_export(results_list):
    df_display = pd.DataFrame(results_list)
    if df_display.empty: return df_display
    
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔍 Tìm mã (Enter để lọc):")
        if search:
            df_display = df_display[df_display['Mã'].str.contains(search.upper(), na=False)]
    
    with col2:
        csv = df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Xuất Excel", csv, "Data.csv", use_container_width=True)
    return df_display
