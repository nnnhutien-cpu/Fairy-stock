import streamlit as st
import pandas as pd
import concurrent.futures
import time
import os
import numpy as np
import streamlit.components.v1 as components
from supabase import create_client
import traceback
from datetime import datetime

from indicators import market_snapshot
from trend_engine import market_recommendation
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex, set_rate_limit, get_expected_latest_trading_date
from indicators import calculate_technical_signals
import trend_engine as te
from ui_layout import render_sidebar, render_market_tab, render_screener_results, render_screener_signals
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt
import valuation
from market_breadth import get_market_breadth, render_breadth_panel, breadth_freshness
from tab_khuyen_nghi import render_recommendation_tab
from screener_suc_bat import render_suc_bat_tab

from tab_ichimoku import render_ichimoku_tab

# thay dòng import tab 5 phút
from tab_tin_hieu_ngay import render_tin_hieu_ngay_tab

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="auto")

# --- 1b. GIAO DIỆN: CSS dùng chung nằm ở ui_kit.py ---
import ui_kit
ui_kit.inject_css()


def sb_header(title: str, subtitle: str = "") -> None:
    """Giữ tên cũ cho tương thích — dùng ui_kit.page_header."""
    ui_kit.page_header(title, subtitle)


# --- 2. KẾT NỐI SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_connection()

# --- CACHE EXCEL CHO TAB "LỌC CUỐI NGÀY" (bot nền GitHub Actions ghi đè file này mỗi ngày) ---
SCREENER_CACHE_FILE = "screener_cache.xlsx"

BLACKLIST = {"BCG", "HBC", "HNG", "POM", "HAG", "ITA", "TGG", "TTB"}

PRIORITY_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "DGC", "DPM", "DCM", "PVD", "PVS", "GEX", "KDH", "NLG", "DXG", "PDR",
    "VND", "HCM", "VCI", "BSI", "CTS", "MSB", "OCB", "EIB", "LPB", "SGB",
    "REE", "GMD", "HAH", "PNJ", "DGW", "FRT", "VTP", "ANV", "VHC", "DBC",
]

# --- 3. KHỞI TẠO BIẾN ---
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []
if 'scan_mode' not in st.session_state:
    st.session_state['scan_mode'] = None

exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, fast_mode = render_sidebar()

# Ô nhập API key vnstock đã bỏ khỏi giao diện; nếu có key trong Secrets thì vẫn dùng.
try:
    active_api_key = str(st.secrets.get("VNSTOCK_API_KEY", "")).strip()
except Exception:
    active_api_key = ""

# TĂNG TỐC ĐỘ LẤY DỮ LIỆU LÊN MỨC TỐI ĐA
if active_api_key:
    try:
        import vnai
        vnai.setup_api_key(active_api_key)
        set_rate_limit(300) # Tăng từ 55 lên 300 request/phút
    except Exception:
        set_rate_limit(150) # Tăng từ 18 lên 150 request/phút
else:
    set_rate_limit(150)

setup_cache_clear_button()

ui_kit.app_title()

# ==========================================
# HÀM ĐỌC CACHE EXCEL (bot nền ghi đè screener_cache.xlsx mỗi ngày)
# ==========================================
def load_screener_cache():
    """Đọc kết quả quét EOD gần nhất từ file Excel do bulk_scan_screener.py tạo.
    Trả về (list_records, scanned_at) hoặc (None, None) nếu chưa có cache / lỗi."""
    if not os.path.exists(SCREENER_CACHE_FILE):
        return None, None
    return _read_screener_cache(os.path.getmtime(SCREENER_CACHE_FILE))


@st.cache_data(show_spinner=False)
def _read_screener_cache(mtime):
    """Đọc Excel 1 lần cho mỗi phiên bản file (khoá cache = thời điểm sửa file)."""
    try:
        cached_df = pd.read_excel(SCREENER_CACHE_FILE, sheet_name="scan")
        scanned_at = (
            cached_df['_scanned_at'].iloc[0]
            if '_scanned_at' in cached_df.columns and len(cached_df) else "?"
        )
        records = cached_df.drop(columns=['_scanned_at'], errors='ignore').to_dict('records')
        return records, scanned_at
    except Exception:
        return None, None

# ==========================================
# HÀM QUÉT CHUNG (ĐÃ TỐI ƯU HÓA TỐC ĐỘ SIÊU TỐC)
# ==========================================
def execute_scan(force_full=False):
    ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
    tickers = get_all_tickers(ex_code)

    if not tickers:
        st.error("⚠️ Lỗi: Không lấy được danh sách mã từ sàn.")
        return []

    ticker_set = set(tickers)
    priority_present = [t for t in PRIORITY_TICKERS if t in ticker_set]
    rest = [t for t in tickers if t not in set(priority_present)]

    if force_full:
        tickers_ordered = priority_present + rest
        effective_max_scan = len(tickers_ordered)
        st.caption(f"🌙 **Quét Cuối Ngày**: Đang quét toàn bộ **{effective_max_scan}** mã trên 3 sàn...")
    else:
        if fast_mode:
            tickers_ordered = priority_present if priority_present else tickers
            effective_max_scan = max_scan
            st.caption(f"⚡ **Quét Nhanh Trong Phiên**: Tập trung {len(tickers_ordered)} mã thanh khoản cao.")
        else:
            tickers_ordered = priority_present + rest
            effective_max_scan = max_scan
            st.caption(f"⚡ **Quét Trong Phiên**: Đang quét **{effective_max_scan}** mã theo thanh trượt.")

    tickers_to_scan = tickers_ordered[:effective_max_scan]
    
    # CẬP NHẬT ETA: Tính toán dựa trên tốc độ xử lý đã được mở khóa (300/phút)
    rate_per_min = 300 if active_api_key else 150
    eta_min = len(tickers_to_scan) / rate_per_min
    st.caption(f"⏱️ Đã mở khóa đa luồng. Ước tính thời gian quét siêu tốc: **~{eta_min:.1f} phút**.")

    scan_start_time = time.time()
    hard_timeout = max(240, min(1200, eta_min * 60 * 4))
    
    live_results_box = st.empty()
    results = []
    error_logs = []

    with st.status(f"🚀 Đang cày {len(tickers_to_scan)} mã... (Chỉ lọc ra các mã thỏa tín hiệu)", expanded=True) as status:
        progress_bar = st.progress(0)
        total = len(tickers_to_scan)
        processed = 0
        timed_out = False
        elapsed = 0.0  # SỬA: tránh NameError nếu vòng lặp không chạy lần nào

        def process_ticker(ticker):
            if ticker in BLACKLIST:
                return {"status": "skip"}
            try:
                # Giảm thời gian lịch sử nếu không cần thiết để tăng tốc fetch
                df = get_stock_data(ticker, days_back=250) 
                if df is None or df.empty:
                    return {"status": "error", "msg": f"{ticker}: Rỗng."}
                try:
                    res = calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
                    if res is None:
                        return {"status": "error", "msg": f"{ticker}: Không tính được chỉ báo."}
                    return {"status": "success", "data": res}
                except Exception as e:
                    return {"status": "error", "msg": f"{ticker}: Lỗi tính toán."}
            except Exception as e:
                return {"status": "error", "msg": f"{ticker}: Lỗi API."}

        # ÉP XUNG MAX WORKERS: 24 luồng cày song song.
        max_workers = 24
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}

            try:
                pending = set(future_to_ticker.keys())
                while pending:
                    remaining_time = hard_timeout - (time.time() - scan_start_time)
                    if remaining_time <= 0:
                        raise concurrent.futures.TimeoutError()

                    done_now, pending = concurrent.futures.wait(
                        pending, timeout=min(2, remaining_time),
                        return_when=concurrent.futures.FIRST_COMPLETED
                    )

                    for future in done_now:
                        processed += 1
                        try:
                            outcome = future.result()
                            if outcome["status"] == "success":
                                results.append(outcome["data"])
                            elif outcome["status"] == "error":
                                error_logs.append(outcome["msg"])
                        except Exception:
                            pass

                    elapsed = time.time() - scan_start_time
                    status.update(label=(
                        f"Đang quét... {processed}/{total} mã | "
                        f"✅ Tìm thấy {len(results)} mã | ⏱️ {elapsed:.0f}s"
                    ))
                    progress_bar.progress(min(processed / total, 1.0))

                    # LỌC LIVE THÔNG MINH: Chỉ hiển thị các mã thỏa mãn "Bộ lọc tín hiệu" 
                    if done_now and results:
                        preview_df = pd.DataFrame(results)
                        if signal_filter != "Tất cả" and 'Trạng thái' in preview_df.columns:
                            preview_df_show = preview_df[preview_df['Trạng thái'] == signal_filter]
                        else:
                            preview_df_show = preview_df
                            
                        live_cols = ["Mã CP", "Giá", "Vol x TB20", "Dòng Tiền", "Xu Hướng", "Trạng thái"]
                        preview_df_live = preview_df_show[[c for c in live_cols if c in preview_df_show.columns]]
                        
                        with live_results_box.container():
                            if not preview_df_live.empty:
                                st.caption(f"🎯 Đang bắt được **{len(preview_df_live)} mã** thỏa mãn điều kiện [{signal_filter}]:")
                                st.dataframe(preview_df_live, width="stretch", hide_index=True)
                            else:
                                st.caption(f"👀 Đang quét {processed}/{total} mã, chưa thấy mã nào thỏa mãn [{signal_filter}]...")
                                
            except concurrent.futures.TimeoutError:
                timed_out = True
                executor.shutdown(wait=False, cancel_futures=True)

        if timed_out:
            status.update(label=f"⏳ Đã dừng quét. Hiển thị {len(results)} mã.", state="complete", expanded=False)
        elif len(results) > 0:
            status.update(label=f"✅ Quét xong toàn bộ! Hoàn thành trong {elapsed:.0f} giây.", state="complete", expanded=False)
        else:
            status.update(label=f"❌ Không tìm thấy dữ liệu!", state="error", expanded=True)

    live_results_box.empty()
    return results

# ==========================================
# TAB 1: THỊ TRƯỜNG (thiết kế lại — xem tab_market.py + market_insights.py)
# ==========================================
from tab_market import render_market


# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU (CHỈ DÀNH CHO CUỐI NGÀY)
# ==========================================
@st.fragment
def render_tab_eod():
    if True:
        sb_header("🔍 Lọc Cổ Phiếu Cuối Ngày", "Quét toàn bộ danh sách mã, bỏ qua giới hạn Fast Mode. Nên chạy sau 15:00")

        col_eod_btn, col_cache_info = st.columns([1, 2], vertical_alignment="center")
        with col_eod_btn:
            eod_scan_button = st.button("🌙 Quét cuối ngày · toàn thị trường", width="stretch", type="primary")

        if eod_scan_button:
            results = execute_scan(force_full=True)
            st.session_state['scan_results'] = results
            st.session_state['scan_mode'] = 'EOD'
            st.session_state['scan_from_cache'] = False
            st.rerun()

        cache_mtime = os.path.getmtime(SCREENER_CACHE_FILE) if os.path.exists(SCREENER_CACHE_FILE) else None
        first_load = not st.session_state.get('scan_results') and st.session_state.get('scan_mode') is None
        cache_changed = (st.session_state.get('scan_from_cache')
                         and st.session_state.get('scan_cache_mtime') != cache_mtime)

        if first_load or cache_changed:
            cached_records, scanned_at = load_screener_cache()
            if cached_records:
                st.session_state['scan_results'] = cached_records
                st.session_state['scan_mode'] = 'EOD'
                st.session_state['scan_from_cache'] = True
                st.session_state['scan_cache_mtime'] = cache_mtime
                st.session_state['scan_cache_at'] = scanned_at
            else:
                with col_cache_info:
                    st.caption("Chưa có cache. Bấm 'Quét cuối ngày' để quét lần đầu, hoặc đợi bot nền GitHub Actions chạy.")

        if st.session_state.get('scan_from_cache'):
            _at = st.session_state.get('scan_cache_at')
            with col_cache_info:
                try:
                    if pd.to_datetime(_at).date() < get_expected_latest_trading_date():
                        st.warning(f"⚠️ Cache quét lúc **{_at}** đã cũ so với phiên gần nhất. Bấm 'Quét cuối ngày' để lấy mới.")
                    else:
                        st.info(f"⚡ Hiển thị {len(st.session_state['scan_results'])} mã từ lần quét lúc **{_at}**.")
                except Exception:
                    st.info(f"⚡ Hiển thị cache quét lúc **{_at}**.")

        if st.session_state.get('scan_mode') == 'EOD' and st.session_state.get('scan_results'):
            raw_df = pd.DataFrame(st.session_state['scan_results'])
            df_display = render_search_and_export(raw_df)
            st.session_state['df_display_cached'] = df_display
            render_screener_results(df_display, signal_filter)
            
        elif st.session_state.get('scan_mode') == 'INTRADAY':
            st.info("⚠️ Bộ nhớ đang lưu kết quả **Quét Trong Phiên**. Hãy chuyển sang tab **Tín Hiệu Trong Phiên** để xem, hoặc bấm Quét cuối ngày để lấy lại dữ liệu toàn thị trường.")
        else:
            st.markdown(
                '<div class="sb-note">Hãy bấm <b>🌙 Quét cuối ngày</b> để bắt đầu lọc dữ liệu toàn bộ thị trường.</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# TAB 3: TÍN HIỆU TRONG PHIÊN (DÙNG FAST MODE - ICHIMOKU/VOLUME)
# ==========================================
@st.fragment
def render_tab_intraday():
    if True:
        sb_header("📡 Tín Hiệu & Cảnh Báo (Trong Phiên)", "Quét nhanh các mã thanh khoản/VN30 (Fast Mode) để theo dõi Volume và Ichimoku realtime")
        
        intraday_scan_button = st.button("⚡ Quét tín hiệu trong phiên", width="stretch", type="primary")

        if intraday_scan_button:
            results = execute_scan(force_full=False)
            st.session_state['scan_results'] = results
            st.session_state['scan_mode'] = 'INTRADAY'
            st.rerun()

        if st.session_state.get('scan_mode') == 'INTRADAY' and st.session_state.get('scan_results'):
            raw_df = pd.DataFrame(st.session_state['scan_results'])
            df_display = render_search_and_export(raw_df)
            st.session_state['df_display_cached'] = df_display
            render_screener_signals(df_display, signal_filter)
            
        elif st.session_state.get('scan_mode') == 'EOD':
            st.info("⚠️ Bộ nhớ đang lưu kết quả **Quét Cuối Ngày**. Hãy bấm 'Quét tín hiệu trong phiên' để lấy dữ liệu realtime mới nhất.")
        else:
            st.markdown(
                '<div class="sb-note">Bấm <b>⚡ Quét tín hiệu trong phiên</b> để cập nhật biến động Volume, dòng tiền và Ichimoku ngay bây giờ.</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# ĐIỀU HƯỚNG — chỉ chạy code của trang đang mở
# SỬA HIỆU NĂNG: st.tabs chạy code của CẢ 7 tab ở mỗi lần tải/tương tác (tab Tín Hiệu Ngày tự
# quét 60 mã, tab Thị Trường tải 4 chỉ số...) dù người dùng chỉ xem 1 tab. Thanh điều hướng
# bên dưới chỉ chạy trang được chọn -> mở app và chuyển trang nhanh hơn nhiều lần.
# ==========================================
from tab_watchlist import render_watchlist


def render_danh_muc():
    ui_kit.page_header("💼 Danh mục", "Bộ lọc 3–5 mã tiềm năng")
    render_watchlist(PRIORITY_TICKERS, p_tenkan, p_kijun, p_senkou_b, p_shift)


PAGES = {
    "🌟 Thị Trường": ("thi-truong", render_market),
    "🔍 Lọc Cuối Ngày": ("loc-cuoi-ngay", render_tab_eod),
    "📡 Tín Hiệu Realtime": ("tin-hieu-realtime", render_tab_intraday),
    "💡 Khuyến Nghị": ("khuyen-nghi",
                      lambda: render_recommendation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift)),
    "☁️ Ichimoku": ("ichimoku",
                    lambda: render_ichimoku_tab(get_stock_data, PRIORITY_TICKERS, p_tenkan, p_kijun, p_senkou_b, p_shift)),
    "🚀 Sức Bật": ("suc-bat", render_suc_bat_tab),
    "💼 Danh mục": ("danh-muc", lambda: render_danh_muc()),
    "🕯️ Tín Hiệu Ngày": ("tin-hieu-ngay", lambda: render_tin_hieu_ngay_tab(PRIORITY_TICKERS)),
}
_slug_to_name = {slug: name for name, (slug, _) in PAGES.items()}
if "nav_page" not in st.session_state:
    # mở đúng trang theo link chia sẻ ?trang=khuyen-nghi
    st.session_state["nav_page"] = _slug_to_name.get(st.query_params.get("trang", ""), "🌟 Thị Trường")

with st.container(key="ct_nav"):
    page = st.segmented_control("Trang", list(PAGES), key="nav_page", selection_mode="single",
                                label_visibility="collapsed")
if page is None:  # bấm lại vào trang đang chọn sẽ bỏ chọn -> giữ trang cũ
    page = st.session_state.get("_nav_last", "🌟 Thị Trường")
st.session_state["_nav_last"] = page
if st.query_params.get("trang") != PAGES[page][0]:
    st.query_params["trang"] = PAGES[page][0]

PAGES[page][1]()import streamlit as st
import pandas as pd
import concurrent.futures
import time
import os
import numpy as np
import streamlit.components.v1 as components
from supabase import create_client
import traceback
from datetime import datetime

from indicators import market_snapshot
from trend_engine import market_recommendation
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex, set_rate_limit, get_expected_latest_trading_date
from indicators import calculate_technical_signals
import trend_engine as te
from ui_layout import render_sidebar, render_market_tab, render_screener_results, render_screener_signals
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt
import valuation
from market_breadth import get_market_breadth, render_breadth_panel, breadth_freshness
from tab_khuyen_nghi import render_recommendation_tab
from screener_suc_bat import render_suc_bat_tab

# THÊM IMPORT MỚI - DANH MỤC
from tab_portfolio_v2 import render_portfolio_v2_tab

# thay dòng import tab 5 phút
from tab_tin_hieu_ngay import render_tin_hieu_ngay_tab

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="auto")

# --- 1b. GIAO DIỆN: CSS dùng chung nằm ở ui_kit.py ---
import ui_kit
ui_kit.inject_css()


def sb_header(title: str, subtitle: str = "") -> None:
    """Giữ tên cũ cho tương thích — dùng ui_kit.page_header."""
    ui_kit.page_header(title, subtitle)


# --- 2. KẾT NỐI SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_connection()

# --- CACHE EXCEL CHO TAB "LỌC CUỐI NGÀY" (bot nền GitHub Actions ghi đè file này mỗi ngày) ---
SCREENER_CACHE_FILE = "screener_cache.xlsx"

BLACKLIST = {"BCG", "HBC", "HNG", "POM", "HAG", "ITA", "TGG", "TTB"}

PRIORITY_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "DGC", "DPM", "DCM", "PVD", "PVS", "GEX", "KDH", "NLG", "DXG", "PDR",
    "VND", "HCM", "VCI", "BSI", "CTS", "MSB", "OCB", "EIB", "LPB", "SGB",
    "REE", "GMD", "HAH", "PNJ", "DGW", "FRT", "VTP", "ANV", "VHC", "DBC",
]

# --- 3. KHỞI TẠO BIẾN ---
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []
if 'scan_mode' not in st.session_state:
    st.session_state['scan_mode'] = None

exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, fast_mode = render_sidebar()

# Ô nhập API key vnstock đã bỏ khỏi giao diện; nếu có key trong Secrets thì vẫn dùng.
try:
    active_api_key = str(st.secrets.get("VNSTOCK_API_KEY", "")).strip()
except Exception:
    active_api_key = ""

# TĂNG TỐC ĐỘ LẤY DỮ LIỆU LÊN MỨC TỐI ĐA
if active_api_key:
    try:
        import vnai
        vnai.setup_api_key(active_api_key)
        set_rate_limit(300) # Tăng từ 55 lên 300 request/phút
    except Exception:
        set_rate_limit(150) # Tăng từ 18 lên 150 request/phút
else:
    set_rate_limit(150)

setup_cache_clear_button()

ui_kit.app_title()

# ==========================================
# HÀM ĐỌC CACHE EXCEL (bot nền ghi đè screener_cache.xlsx mỗi ngày)
# ==========================================
def load_screener_cache():
    """Đọc kết quả quét EOD gần nhất từ file Excel do bulk_scan_screener.py tạo.
    Trả về (list_records, scanned_at) hoặc (None, None) nếu chưa có cache / lỗi."""
    if not os.path.exists(SCREENER_CACHE_FILE):
        return None, None
    return _read_screener_cache(os.path.getmtime(SCREENER_CACHE_FILE))


@st.cache_data(show_spinner=False)
def _read_screener_cache(mtime):
    """Đọc Excel 1 lần cho mỗi phiên bản file (khoá cache = thời điểm sửa file)."""
    try:
        cached_df = pd.read_excel(SCREENER_CACHE_FILE, sheet_name="scan")
        scanned_at = (
            cached_df['_scanned_at'].iloc[0]
            if '_scanned_at' in cached_df.columns and len(cached_df) else "?"
        )
        records = cached_df.drop(columns=['_scanned_at'], errors='ignore').to_dict('records')
        return records, scanned_at
    except Exception:
        return None, None

# ==========================================
# HÀM QUÉT CHUNG (ĐÃ TỐI ƯU HÓA TỐC ĐỘ SIÊU TỐC)
# ==========================================
def execute_scan(force_full=False):
    ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
    tickers = get_all_tickers(ex_code)

    if not tickers:
        st.error("⚠️ Lỗi: Không lấy được danh sách mã từ sàn.")
        return []

    ticker_set = set(tickers)
    priority_present = [t for t in PRIORITY_TICKERS if t in ticker_set]
    rest = [t for t in tickers if t not in set(priority_present)]

    if force_full:
        tickers_ordered = priority_present + rest
        effective_max_scan = len(tickers_ordered)
        st.caption(f"🌙 **Quét Cuối Ngày**: Đang quét toàn bộ **{effective_max_scan}** mã trên 3 sàn...")
    else:
        if fast_mode:
            tickers_ordered = priority_present if priority_present else tickers
            effective_max_scan = max_scan
            st.caption(f"⚡ **Quét Nhanh Trong Phiên**: Tập trung {len(tickers_ordered)} mã thanh khoản cao.")
        else:
            tickers_ordered = priority_present + rest
            effective_max_scan = max_scan
            st.caption(f"⚡ **Quét Trong Phiên**: Đang quét **{effective_max_scan}** mã theo thanh trượt.")

    tickers_to_scan = tickers_ordered[:effective_max_scan]
    
    # CẬP NHẬT ETA: Tính toán dựa trên tốc độ xử lý đã được mở khóa (300/phút)
    rate_per_min = 300 if active_api_key else 150
    eta_min = len(tickers_to_scan) / rate_per_min
    st.caption(f"⏱️ Đã mở khóa đa luồng. Ước tính thời gian quét siêu tốc: **~{eta_min:.1f} phút**.")

    scan_start_time = time.time()
    hard_timeout = max(240, min(1200, eta_min * 60 * 4))
    
    live_results_box = st.empty()
    results = []
    error_logs = []

    with st.status(f"🚀 Đang cày {len(tickers_to_scan)} mã... (Chỉ lọc ra các mã thỏa tín hiệu)", expanded=True) as status:
        progress_bar = st.progress(0)
        total = len(tickers_to_scan)
        processed = 0
        timed_out = False
        elapsed = 0.0  # SỬA: tránh NameError nếu vòng lặp không chạy lần nào

        def process_ticker(ticker):
            if ticker in BLACKLIST:
                return {"status": "skip"}
            try:
                # Giảm thời gian lịch sử nếu không cần thiết để tăng tốc fetch
                df = get_stock_data(ticker, days_back=250) 
                if df is None or df.empty:
                    return {"status": "error", "msg": f"{ticker}: Rỗng."}
                try:
                    res = calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
                    if res is None:
                        return {"status": "error", "msg": f"{ticker}: Không tính được chỉ báo."}
                    return {"status": "success", "data": res}
                except Exception as e:
                    return {"status": "error", "msg": f"{ticker}: Lỗi tính toán."}
            except Exception as e:
                return {"status": "error", "msg": f"{ticker}: Lỗi API."}

        # ÉP XUNG MAX WORKERS: 24 luồng cày song song.
        max_workers = 24
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}

            try:
                pending = set(future_to_ticker.keys())
                while pending:
                    remaining_time = hard_timeout - (time.time() - scan_start_time)
                    if remaining_time <= 0:
                        raise concurrent.futures.TimeoutError()

                    done_now, pending = concurrent.futures.wait(
                        pending, timeout=min(2, remaining_time),
                        return_when=concurrent.futures.FIRST_COMPLETED
                    )

                    for future in done_now:
                        processed += 1
                        try:
                            outcome = future.result()
                            if outcome["status"] == "success":
                                results.append(outcome["data"])
                            elif outcome["status"] == "error":
                                error_logs.append(outcome["msg"])
                        except Exception:
                            pass

                    elapsed = time.time() - scan_start_time
                    status.update(label=(
                        f"Đang quét... {processed}/{total} mã | "
                        f"✅ Tìm thấy {len(results)} mã | ⏱️ {elapsed:.0f}s"
                    ))
                    progress_bar.progress(min(processed / total, 1.0))

                    # LỌC LIVE THÔNG MINH: Chỉ hiển thị các mã thỏa mãn "Bộ lọc tín hiệu" 
                    if done_now and results:
                        preview_df = pd.DataFrame(results)
                        if signal_filter != "Tất cả" and 'Trạng thái' in preview_df.columns:
                            preview_df_show = preview_df[preview_df['Trạng thái'] == signal_filter]
                        else:
                            preview_df_show = preview_df
                            
                        live_cols = ["Mã CP", "Giá", "Vol x TB20", "Dòng Tiền", "Xu Hướng", "Trạng thái"]
                        preview_df_live = preview_df_show[[c for c in live_cols if c in preview_df_show.columns]]
                        
                        with live_results_box.container():
                            if not preview_df_live.empty:
                                st.caption(f"🎯 Đang bắt được **{len(preview_df_live)} mã** thỏa mãn điều kiện [{signal_filter}]:")
                                st.dataframe(preview_df_live, width="stretch", hide_index=True)
                            else:
                                st.caption(f"👀 Đang quét {processed}/{total} mã, chưa thấy mã nào thỏa mãn [{signal_filter}]...")
                                
            except concurrent.futures.TimeoutError:
                timed_out = True
                executor.shutdown(wait=False, cancel_futures=True)

        if timed_out:
            status.update(label=f"⏳ Đã dừng quét. Hiển thị {len(results)} mã.", state="complete", expanded=False)
        elif len(results) > 0:
            status.update(label=f"✅ Quét xong toàn bộ! Hoàn thành trong {elapsed:.0f} giây.", state="complete", expanded=False)
        else:
            status.update(label=f"❌ Không tìm thấy dữ liệu!", state="error", expanded=True)

    live_results_box.empty()
    return results

# ==========================================
# TAB 1: THỊ TRƯỜNG (thiết kế lại — xem tab_market.py + market_insights.py)
# ==========================================
from tab_market import render_market


# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU (CHỈ DÀNH CHO CUỐI NGÀY)
# ==========================================
@st.fragment
def render_tab_eod():
    if True:
        sb_header("🔍 Lọc Cổ Phiếu Cuối Ngày", "Quét toàn bộ danh sách mã, bỏ qua giới hạn Fast Mode. Nên chạy sau 15:00")

        col_eod_btn, col_cache_info = st.columns([1, 2], vertical_alignment="center")
        with col_eod_btn:
            eod_scan_button = st.button("🌙 Quét cuối ngày · toàn thị trường", width="stretch", type="primary")

        if eod_scan_button:
            results = execute_scan(force_full=True)
            st.session_state['scan_results'] = results
            st.session_state['scan_mode'] = 'EOD'
            st.session_state['scan_from_cache'] = False
            st.rerun()

        cache_mtime = os.path.getmtime(SCREENER_CACHE_FILE) if os.path.exists(SCREENER_CACHE_FILE) else None
        first_load = not st.session_state.get('scan_results') and st.session_state.get('scan_mode') is None
        cache_changed = (st.session_state.get('scan_from_cache')
                         and st.session_state.get('scan_cache_mtime') != cache_mtime)

        if first_load or cache_changed:
            cached_records, scanned_at = load_screener_cache()
            if cached_records:
                st.session_state['scan_results'] = cached_records
                st.session_state['scan_mode'] = 'EOD'
                st.session_state['scan_from_cache'] = True
                st.session_state['scan_cache_mtime'] = cache_mtime
                st.session_state['scan_cache_at'] = scanned_at
            else:
                with col_cache_info:
                    st.caption("Chưa có cache. Bấm 'Quét cuối ngày' để quét lần đầu, hoặc đợi bot nền GitHub Actions chạy.")

        if st.session_state.get('scan_from_cache'):
            _at = st.session_state.get('scan_cache_at')
            with col_cache_info:
                try:
                    if pd.to_datetime(_at).date() < get_expected_latest_trading_date():
                        st.warning(f"⚠️ Cache quét lúc **{_at}** đã cũ so với phiên gần nhất. Bấm 'Quét cuối ngày' để lấy mới.")
                    else:
                        st.info(f"⚡ Hiển thị {len(st.session_state['scan_results'])} mã từ lần quét lúc **{_at}**.")
                except Exception:
                    st.info(f"⚡ Hiển thị cache quét lúc **{_at}**.")

        if st.session_state.get('scan_mode') == 'EOD' and st.session_state.get('scan_results'):
            raw_df = pd.DataFrame(st.session_state['scan_results'])
            df_display = render_search_and_export(raw_df)
            st.session_state['df_display_cached'] = df_display
            render_screener_results(df_display, signal_filter)
            
        elif st.session_state.get('scan_mode') == 'INTRADAY':
            st.info("⚠️ Bộ nhớ đang lưu kết quả **Quét Trong Phiên**. Hãy chuyển sang tab **Tín Hiệu Trong Phiên** để xem, hoặc bấm Quét cuối ngày để lấy lại dữ liệu toàn thị trường.")
        else:
            st.markdown(
                '<div class="sb-note">Hãy bấm <b>🌙 Quét cuối ngày</b> để bắt đầu lọc dữ liệu toàn bộ thị trường.</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# TAB 3: TÍN HIỆU TRONG PHIÊN (DÙNG FAST MODE - ICHIMOKU/VOLUME)
# ==========================================
@st.fragment
def render_tab_intraday():
    if True:
        sb_header("📡 Tín Hiệu & Cảnh Báo (Trong Phiên)", "Quét nhanh các mã thanh khoản/VN30 (Fast Mode) để theo dõi Volume và Ichimoku realtime")
        
        intraday_scan_button = st.button("⚡ Quét tín hiệu trong phiên", width="stretch", type="primary")

        if intraday_scan_button:
            results = execute_scan(force_full=False)
            st.session_state['scan_results'] = results
            st.session_state['scan_mode'] = 'INTRADAY'
            st.rerun()

        if st.session_state.get('scan_mode') == 'INTRADAY' and st.session_state.get('scan_results'):
            raw_df = pd.DataFrame(st.session_state['scan_results'])
            df_display = render_search_and_export(raw_df)
            st.session_state['df_display_cached'] = df_display
            render_screener_signals(df_display, signal_filter)
            
        elif st.session_state.get('scan_mode') == 'EOD':
            st.info("⚠️ Bộ nhớ đang lưu kết quả **Quét Cuối Ngày**. Hãy bấm 'Quét tín hiệu trong phiên' để lấy dữ liệu realtime mới nhất.")
        else:
            st.markdown(
                '<div class="sb-note">Bấm <b>⚡ Quét tín hiệu trong phiên</b> để cập nhật biến động Volume, dòng tiền và Ichimoku ngay bây giờ.</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# ĐIỀU HƯỚNG — chỉ chạy code của trang đang mở
# SỬA HIỆU NĂNG: st.tabs chạy code của CẢ 7 tab ở mỗi lần tải/tương tác (tab Tín Hiệu Ngày tự
# quét 60 mã, tab Thị Trường tải 4 chỉ số...) dù người dùng chỉ xem 1 tab. Thanh điều hướng
# bên dưới chỉ chạy trang được chọn -> mở app và chuyển trang nhanh hơn nhiều lần.
# ==========================================
from tab_watchlist import render_watchlist


def render_danh_muc():
    ui_kit.page_header("💼 Danh mục", "Bộ lọc 3–5 mã tiềm năng · danh mục 4 mã × 25%")
    t1, t2 = st.tabs(["✨ Mã tiềm năng", "🧺 Danh mục 4 mã × 25%"])
    with t1:
        render_watchlist(PRIORITY_TICKERS, p_tenkan, p_kijun, p_senkou_b, p_shift)
    with t2:
        render_portfolio_v2_tab(PRIORITY_TICKERS)


PAGES = {
    "🌟 Thị Trường": ("thi-truong", render_market),
    "🔍 Lọc Cuối Ngày": ("loc-cuoi-ngay", render_tab_eod),
    "📡 Tín Hiệu Realtime": ("tin-hieu-realtime", render_tab_intraday),
    "💡 Khuyến Nghị": ("khuyen-nghi",
                      lambda: render_recommendation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift)),
    "🚀 Sức Bật": ("suc-bat", render_suc_bat_tab),
    "💼 Danh mục": ("danh-muc", lambda: render_danh_muc()),
    "🕯️ Tín Hiệu Ngày": ("tin-hieu-ngay", lambda: render_tin_hieu_ngay_tab(PRIORITY_TICKERS)),
}
_slug_to_name = {slug: name for name, (slug, _) in PAGES.items()}
if "nav_page" not in st.session_state:
    # mở đúng trang theo link chia sẻ ?trang=khuyen-nghi
    st.session_state["nav_page"] = _slug_to_name.get(st.query_params.get("trang", ""), "🌟 Thị Trường")

with st.container(key="ct_nav"):
    page = st.segmented_control("Trang", list(PAGES), key="nav_page", selection_mode="single",
                                label_visibility="collapsed")
if page is None:  # bấm lại vào trang đang chọn sẽ bỏ chọn -> giữ trang cũ
    page = st.session_state.get("_nav_last", "🌟 Thị Trường")
st.session_state["_nav_last"] = page
if st.query_params.get("trang") != PAGES[page][0]:
    st.query_params["trang"] = PAGES[page][0]

PAGES[page][1]()
