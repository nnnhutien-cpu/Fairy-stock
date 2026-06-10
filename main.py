import streamlit as st
import pandas as pd
import concurrent.futures
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex
from indicators import calculate_technical_signals
from ui_layout import render_sidebar, render_market_tab, render_screener_results
from ux_components import setup_cache_clear_button, render_search_and_export 
import charts as c  
import backtester as bt  

# 1. Cấu hình khung giao diện Streamlit (Rộng toàn màn hình)
st.set_page_config(
    page_title="Cô Tiên Stock", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Khởi tạo trạng thái lưu trữ kết quả quét
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

# 2. Hiển thị Thanh điều khiển Sidebar
exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift = render_sidebar()

# Kích hoạt nút dọn dẹp Cache
setup_cache_clear_button()

# Tiêu đề chính
st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật Chuyên Sâu")

# 3. Phân rã cấu trúc giao diện thành 4 Tab
tab_market, tab_screener, tab_simulation, tab_backtest = st.tabs([
    "📊 TỔNG QUAN VN-INDEX",
    "🚀 BỘ LỌC CỔ PHIẾU REAL-TIME",
    "🔮 MÔ PHỎNG ĐỒ THỊ PHÂN TẦNG",
    "⏱️ BACKTEST CHIẾN LƯỢC 3 PHÚT"
])

# =====================================================================
# TAB 1: DIỄN BIẾN THỊ TRƯỜNG CHUNG
# =====================================================================
with tab_market:
    st.subheader("Diễn biến chỉ số VN-Index và Thanh khoản dòng tiền")
    try:
        # [ĐÃ FIX] Lấy dữ liệu VN-INDEX trước, sau đó mới truyền vào hàm render
        chart_df, df_today = get_vnindex_data()
        render_market_tab(chart_df, df_today)
    except Exception as e:
        st.error(f"❌ Không thể tải dữ liệu thị trường chung: {e}")

# =====================================================================
# TAB 2: CỖ MÁY QUÉT VÀ LỌC CỔ PHIẾU ĐA LUỒNG
# =====================================================================
with tab_screener:
    st.subheader("Hệ thống quét dòng tiền và chấm điểm kỹ thuật toàn thị trường")
    try:
        # [ĐÃ FIX] Bốc danh sách mã cổ phiếu theo sàn trước
        tickers_list = get_all_tickers(exchange_choice)
        # Truyền danh sách mã vào cỗ máy quét
        render_screener_results(tickers_list, signal_filter, max_scan)
    except Exception as e:
        st.error(f"❌ Lỗi khi khởi chạy bộ lọc cổ phiếu: {e}")

# =====================================================================
# TAB 3: MÔ PHỎNG CHI TIẾT TÍN HIỆU MÃ THEO ICHIMOKU DỰA TRÊN VOLUME
# =====================================================================
with tab_simulation:
    st.subheader("Phân tích kỹ thuật chuyên sâu cho từng mã riêng lẻ")
    
    ticker = st.text_input("Nhập mã cổ phiếu của bạn (Ví dụ: SSI, HPG, TCB):", value="SSI").upper().strip()
    
    if ticker:
        try:
            c.render_ichimoku_simulation_chart(ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
            render_search_and_export(ticker)
        except Exception as e:
            st.warning(f"⚠️ Biểu đồ mô phỏng mã {ticker} đang gặp gián đoạn dữ liệu: {e}")

# =====================================================================
# TAB 4: HỆ THỐNG BACKTEST KHUNG ĐỒ THỊ 3 PHÚT (QUANT/ALGO)
# =====================================================================
with tab_backtest:
    st.subheader("Kiểm thử chiến lược giao dịch trong quá khứ dựa trên nến phút")
    try:
        bt.render_backtest_layout()
    except Exception as e:
        st.error(f"❌ Không thể khởi chạy môi trường Backtest: {e}")
