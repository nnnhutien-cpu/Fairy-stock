import streamlit as st
import pandas as pd
import concurrent.futures
import streamlit.components.v1 as components 
from supabase import create_client

from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt 

# --- 1. CẤU HÌNH TRANG (Lệnh này bắt buộc phải nằm đầu tiên) ---
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# --- 1b. GIAO DIỆN: MÀU SẮC & PHÔNG CHỮ ---
st.markdown("""
<style>
    /* Font tiếng Việt đẹp cho toàn app */
    @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"], .stMarkdown, .stButton, .stTextInput, .stSelectbox {
        font-family: 'Be Vietnam Pro', sans-serif !important;
    }

    /* Nền tổng thể tối sang trọng */
    .stApp {
        background: linear-gradient(180deg, #0b1120 0%, #111a2e 100%);
        color: #e6edf3;
    }

    /* Tiêu đề */
    h1, h2, h3, .stSubheader {
        color: #f5d67b !important;   /* vàng ánh kim */
        font-weight: 700 !important;
        letter-spacing: .3px;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #0d1526;
        border-right: 1px solid #1e2b45;
    }

    /* Các khối Metric */
    div[data-testid="stMetric"] {
        background: #131d33;
        border: 1px solid #22314f;
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 4px 14px rgba(0,0,0,.35);
    }
    div[data-testid="stMetricValue"] { color: #ffffff; font-weight: 700; }
    div[data-testid="stMetricLabel"] { color: #9fb3d1; }

    /* Nút bấm */
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid #2b6cff;
        transition: all .15s ease;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #2b6cff, #1e9e6a);
        color: #fff;
        border: none;
    }
    .stButton > button:hover { transform: translateY(-1px); filter: brightness(1.08); }

    /* Thanh tab */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: #0d1526;
        padding: 6px;
        border-radius: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 18px;
        color: #9fb3d1;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #2b6cff, #1e9e6a) !important;
        color: #ffffff !important;
    }

    /* Ô nhập liệu & bảng */
    .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        background: #131d33; color: #e6edf3; border-radius: 8px;
    }
    .stDataFrame { border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI SUPABASE TRỰC TIẾP (Dành riêng để nuôi Tab 5 Báo Cáo) ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 3. KHỞI TẠO BIẾN CHO GIAO DIỆN ---
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

# Đọc các thông số Ichimoku động từ Sidebar bên trái
exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()

# [GỌI HÀM UX] Tạo nút xóa Cache
setup_cache_clear_button()

# --- 4. TẠO 5 TAB (DÒNG BỊ THIẾU GÂY LỖI NameError) ---
tab_market, tab_screener, tab_simulation, tab_backtest, tab_reports = st.tabs([
    "🌟 Thị Trường", "🔍 Bộ Lọc", "🔮 Mô Phỏng", "🛠️ Backtest", "📑 Báo Cáo"
])
