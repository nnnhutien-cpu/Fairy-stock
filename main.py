import streamlit as st
import pandas as pd
import concurrent.futures
import time
import streamlit.components.v1 as components
from supabase import create_client
import traceback
from datetime import datetime

from indicators import market_snapshot
from trend_engine import market_recommendation
from tab_accumulation import render_accumulation_tab
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex, set_rate_limit
from indicators import calculate_technical_signals
import trend_engine as te
from ui_layout import render_sidebar, render_market_tab, render_screener_results, render_screener_signals
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt
import valuation
from market_breadth import get_market_breadth, get_index_groups, render_breadth_panel

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# --- 1b. GIAO DIỆN: TÍM ĐẬM SANG TRỌNG + FONT + HÒA HEADER ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"], .stMarkdown, .stButton, .stTextInput, .stSelectbox, .stDataFrame {
        font-family: 'Sora', sans-serif !important;
    }

    .stApp {
        background: linear-gradient(180deg, #0f0a1f 0%, #16112e 100%);
        color: #dcd6ec;
    }

    header[data-testid="stHeader"] { background: #0f0a1f !important; }
    header[data-testid="stHeader"] a, header[data-testid="stToolbar"] * { color: #b9aee0 !important; }

    h1 { font-size: 2rem !important; line-height: 1.25 !important; }
    h2, .stSubheader { font-size: 1.4rem !important; }
    h3 { font-size: 1.15rem !important; }
    h1, h2, h3, .stSubheader { color: #a394d4 !important; font-weight: 700 !important; letter-spacing: .2px; }

    section[data-testid="stSidebar"] { background: #120d26; border-right: 1px solid #241a45; }
    section[data-testid="stSidebar"] .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }

    .block-container {
        padding-top: 2.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
        max-width: 100% !important;
    }

    div[data-testid="stMetric"] {
        background: #1a1436;
        border: 1px solid #2c2151;
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 4px 14px rgba(40,25,80,.35);
    }
    div[data-testid="stMetricValue"] { color: #f2eeff; font-weight: 700; font-size: 1.5rem !important; }
    div[data-testid="stMetricLabel"] { color: #a99fcf; font-size: .85rem !important; }

    .stButton > button {
        border-radius: 10px; font-weight: 600; border: 1px solid #4a3a7a; transition: all .15s ease;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #4c1d95, #6d28d9); color: #efe9ff; border: none;
    }
    .stButton > button:hover { transform: translateY(-1px); filter: brightness(1.12); }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: #120d26; padding: 6px; border-radius: 12px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 6px 14px; color: #a99fcf; font-weight: 600; font-size: .9rem; }
    .stTabs [aria-selected="true"] { background: linear-gradient(90deg, #4c1d95, #6d28d9) !important; color: #ffffff !important; }

    [data-testid="stAppDeployButton"] button, .stDeployButton button, button[title="Manage app"] {
        background: linear-gradient(90deg, #4c1d95, #6d28d9) !important; color: #efe9ff !important;
        border: none !important; border-radius: 8px !important; font-weight: 600 !important;
    }
    #MainMenu button, [data-testid="stMainMenu"] button { color: #b9aee0 !important; }
    #MainMenu button:hover { background: #2c2151 !important; }
    [data-testid="stSidebarCollapseButton"] button, [data-testid="collapsedControl"] button {
        color: #b9aee0 !important; background: #1a1436 !important; border-radius: 8px !important;
    }
    [data-testid="StyledFullScreenButton"] { color: #b9aee0 !important; }
    .stSlider [role="slider"] { background: #6d28d9 !important; }

    .stTextInput input, .stSelectbox div[data-baseweb="select"] { background: #1a1436; color: #dcd6ec; border-radius: 8px; }
    .stDataFrame { border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

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

exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, vnstock_api_key, fast_mode = render_sidebar()

active_api_key = vnstock_api_key.strip()
if not active_api_key:
    try:
        active_api_key = st.secrets.get("VNSTOCK_API_KEY", "")
    except Exception:
        active_api_key = ""
if active_api_key:
    try:
        import vnai
        vnai.setup_api_key(active_api_key)
        set_rate_limit(55)
    except Exception:
        set_rate_limit(18)
else:
    set_rate_limit(18)

setup_cache_clear_button()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật")

# --- 4. TẠO 8 TAB ---
tab_market, tab_screener, tab_results, tab_signals, tab_simulation, tab_backtest, tab_reports, tab_accum = st.tabs([
    "🌟 Thị Trường", "🔍 Bộ Lọc", "📊 Kết Quả Quét", "📡 Tín Hiệu & Cảnh Báo",
    "🔮 Mô Phỏng", "🛠️ Backtest", "📑 Báo Cáo", "🧭 Tích Lũy"
])

# ==========================================
# TAB 1: THỊ TRƯỜNG CHUNG
# ==========================================
with tab_market:
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("🌟 TỔNG QUAN THỊ TRƯỜNG REAL-TIME")
    with col_btn:
        if st.button("🔄 CẬP NHẬT DỮ LIỆU", type="primary", use_container_width=True):
            get_intraday_vnindex.clear()
            st.rerun()
    st.divider()

    intraday_df = get_intraday_vnindex()
    chart_df, df_today = None, None
    current_index = 0

    if intraday_df is not None and not intraday_df.empty:
        col_mapping = {}
        for col in intraday_df.columns:
            lower_col = str(col).lower().strip()
            if lower_col in ['close', 'price', 'c', 'điểm', 'index', 'indexvalue']:
                col_mapping[col] = 'close'
            elif lower_col in ['volume', 'vol', 'v', 'khối lượng', 'matchvolume']:
                col_mapping[col] = 'volume'
            elif lower_col in ['time', 't', 'thời gian']:
                col_mapping[col] = 'time'

        intraday_df.rename(columns=col_mapping, inplace=True)

        if 'time' in intraday_df.columns and 'volume' in intraday_df.columns and 'close' in intraday_df.columns:
            intraday_df['volume'] = pd.to_numeric(intraday_df['volume'], errors='coerce').fillna(0)
            intraday_df['close'] = pd.to_numeric(intraday_df['close'], errors='coerce').fillna(0)
            intraday_df['time'] = pd.to_datetime(intraday_df['time'])
            intraday_df['date'] = intraday_df['time'].dt.date
            intraday_df['hour_min'] = intraday_df['time'].dt.strftime('%H:%M')

            intraday_df = intraday_df[(intraday_df['hour_min'] >= '09:00') & (intraday_df['hour_min'] <= '15:00')]

            dates = sorted(intraday_df['date'].unique())
            if len(dates) >= 2:
                today_date = dates[-1]
                yest_date = dates[-2]

                df_today = intraday_df[intraday_df['date'] == today_date].copy()
                df_yest = intraday_df[intraday_df['date'] == yest_date].copy()

                df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
                df_yest['Vol_Hôm_Qua'] = df_yest['volume'].cumsum()

                current_index = df_today['close'].iloc[-1] if not df_today.empty else 0
                prev_index = df_yest['close'].iloc[-1] if not df_yest.empty else current_index
                index_change = current_index - prev_index

                current_vol = df_today['Vol_Hôm_Nay'].iloc[-1] if not df_today.empty else 0
                prev_vol = df_yest['Vol_Hôm_Qua'].iloc[-1] if not df_yest.empty else 0
                vol_change = current_vol - prev_vol

                m1, m2, m3 = st.columns(3)
                m1.metric("📊 Chỉ số VN-INDEX", f"{current_index:,.2f} đ", f"{index_change:,.2f} đ")
                m2.metric("💰 Thanh khoản Hôm Nay", f"{current_vol:,.0f} CP", f"{vol_change:,.0f} CP" if vol_change != 0 else None)
                m3.metric("⏳ Thanh khoản Hôm Qua (EOD)", f"{prev_vol:,.0f} CP")

                times_morning = pd.date_range("09:00", "11:30", freq="min").strftime('%H:%M').tolist()
                times_afternoon = pd.date_range("13:00", "15:00", freq="min").strftime('%H:%M').tolist()
                time_df = pd.DataFrame({'hour_min': times_morning + times_afternoon})

                df_yest_agg = df_yest.groupby('hour_min')['Vol_Hôm_Qua'].last().reset_index()
                df_today_agg = df_today.groupby('hour_min')['Vol_Hôm_Nay'].last().reset_index()

                chart_df = pd.merge(time_df, df_yest_agg, on='hour_min', how='left')
                chart_df = pd.merge(chart_df, df_today_agg, on='hour_min', how='left')

                chart_df['Vol_Hôm_Qua'] = chart_df['Vol_Hôm_Qua'].ffill()

                if not df_today.empty:
                    max_time_actual = df_today['hour_min'].max()
                    chart_df['Vol_Hôm_Nay'] = chart_df['Vol_Hôm_Nay'].ffill()
                    chart_df.loc[chart_df['hour_min'] > max_time_actual, 'Vol_Hôm_Nay'] = None
                    st.info(f"🕒 Tình trạng luồng dữ liệu: API VN-INDEX đang trả số thực tế đến mốc **{max_time_actual}**")

                chart_df.set_index('hour_min', inplace=True)
    else:
        st.warning("⚠️ Đang chờ dữ liệu VN-INDEX từ API. Vui lòng tải lại trang sau ít phút...")

    render_market_tab(chart_df, df_today)

    # ============================================================
    # PHÂN TÍCH XU HƯỚNG & KHUYẾN NGHỊ THỊ TRƯỜNG
    # ============================================================
    st.markdown("---")
    st.markdown("### 🧠 Phân tích Xu hướng & Khuyến nghị Thị trường")

    try:
        snap = market_snapshot(symbol="VNINDEX", days=250)
    except Exception as e:
        st.warning(f"⚠️ Không lấy được dữ liệu phân tích thị trường: {e}")
        snap = None

    if snap is not None:
        try:
            reco = market_recommendation(snap)
        except Exception as e:
            st.warning(f"⚠️ Không tính được khuyến nghị: {e}")
            reco = None

        # --- Hàng 1: Xu hướng giá | Dòng tiền ---
        c1, c2 = st.columns(2)

        with c1:
            with st.container(border=True):
                st.markdown("#### 📈 Xu hướng giá")
                st.markdown(f"### {snap.get('trend_text', '—')}")
                st.caption(snap.get("ma20_text", ""))

                m1, m2, m3 = st.columns(3)
                m1.metric("MA20",  f"{snap['ma20']:.1f}"  if snap.get('ma20')  else "—")
                m2.metric("MA50",  f"{snap['ma50']:.1f}"  if snap.get('ma50')  else "—")
                m3.metric("MA200", f"{snap['ma200']:.1f}" if snap.get('ma200') else "—")

                st.markdown(
                    f"**Hỗ trợ gần:** `{snap.get('support', 0):.1f}` &nbsp;•&nbsp; "
                    f"**Kháng cự:** `{snap.get('resistance', 0):.1f}`"
                )

        with c2:
            with st.container(border=True):
                st.markdown("#### 🔊 Dòng tiền (Volume)")
                st.markdown(f"### {snap.get('vol_text', '—')}")

                v1, v2 = st.columns(2)
                v1.metric("Vol hôm nay", f"{snap.get('vol_today', 0):,.0f}")
                v2.metric("TB 20 phiên", f"{snap.get('vol_avg', 0):,.0f}")

                vol_ratio = snap.get("vol_ratio", 0) or 0
                st.progress(
                    min(vol_ratio / 2.0, 1.0),
                    text=f"Tỷ lệ: {vol_ratio}x trung bình"
                )

        # --- Hàng 2: Chỉ báo KT | Định giá P/E ---
        c3, c4 = st.columns(2)

        with c3:
            with st.container(border=True):
                st.markdown("#### 📊 Chỉ báo kỹ thuật")
                st.markdown(f"**RSI(14):** `{snap.get('rsi', '—')}` — {snap.get('rsi_text', '')}")
                st.markdown(
                    f"**MACD:** `{snap.get('macd', '—')}` &nbsp;|&nbsp; "
                    f"**Signal:** `{snap.get('macd_signal', '—')}`"
                )
                macd_color = snap.get('macd_color', 'gray')
                macd_cross = snap.get('macd_cross', '—')
                st.markdown(f"**Trạng thái MACD:** :{macd_color}[{macd_cross}]")

                st.divider()

                # --- BREADTH THỊ TRƯỜNG ---
                scan_results = st.session_state.get('scan_results', [])
                breadth = get_market_breadth(scan_results)
                render_breadth_panel(breadth)

        with c4:
            with st.container(border=True):
                st.markdown("#### 💰 Định giá P/E (20 năm)")

                pe_now   = valuation.get_current_pe(current_index)
                pe_hist  = valuation.get_pe_history(years=20)
                pe_stats = valuation.pe_stats(pe_hist, pe_now)

                col_pe1, col_pe2 = st.columns([1, 1])
                with col_pe1:
                    st.metric(
                        "P/E hiện tại",
                        f"{pe_stats['pe_now']:.1f}x" if pe_stats['pe_now'] else "—",
                        delta=f"{pe_stats['pct_vs_avg']:+.1f}% vs TB" if pe_stats.get('pct_vs_avg') else None,
                        delta_color="inverse"
                    )
                with col_pe2:
                    st.metric(
                        "Trung bình 20 năm",
                        f"{pe_stats['mean']:.1f}x" if pe_stats.get('mean') else "—",
                        delta=f"{pe_stats['zscore']:+.2f}σ" if pe_stats.get('zscore') else None
                    )

                pct = pe_stats.get('percentile')
                if pct is not None:
                    color = "🟢" if pct < 25 else "🟡" if pct < 75 else "🔴"
                    label = "RẺ" if pct < 25 else "HỢP LÝ" if pct < 75 else "ĐẮT"
                    st.progress(pct / 100, text=f"{color} Percentile: {pct:.0f}% — {label}")

                if pe_stats.get('comment'):
                    st.info(pe_stats['comment'])

                if pe_hist is not None and not pe_hist.empty:
                    with st.expander("📈 Xem P/E 20 năm", expanded=False):
                        st.line_chart(pe_hist.set_index("date")["pe"], height=200)

        # ============================================================
        # 💡 KHUYẾN NGHỊ HÀNH ĐỘNG (tổng hợp tất cả)
        # ============================================================
        if reco is not None:
            st.markdown("---")
            st.markdown("### 💡 Khuyến nghị Hành động (tổng hợp tất cả)")
            with st.container(border=True):
                st.markdown(f"### :{reco.get('color', 'gray')}[{reco.get('action', '—')}]")

                s1, s2 = st.columns(2)
                s1.metric("📈 Nên nắm giữ CP", f"{reco.get('stock', 0)}%")
                s2.metric("💵 Nên giữ tiền mặt", f"{reco.get('cash', 0)}%")

                stock_pct = reco.get("stock", 0) or 0
                cash_pct  = reco.get("cash", 0) or 0
                st.progress(stock_pct / 100, text=f"Tỷ trọng CP {stock_pct}% / Tiền {cash_pct}%")

                with st.expander("📋 Lý do khuyến nghị", expanded=True):
                    for r in reco.get("reasons", []):
                        st.markdown(f"- {r}")

                st.caption("⚠️ Khuyến nghị dựa trên phân tích kỹ thuật, không phải tư vấn đầu tư chính thức.")

    # ============================================================
    # 🆕 SỨC KHỎE THỊ TRƯỜNG (Breadth)
    # ============================================================
    st.markdown("---")
    st.markdown("### 🏥 Sức khỏe Thị trường (Breadth)")

    groups  = get_index_groups()
    breadth_full = get_market_breadth()

    # ===== BẢNG 1: INDEX GROUPS =====
    with st.container(border=True):
        st.markdown("#### 📊 Index Groups (cập nhật mỗi 3 phút)")

        h1, h2, h3, h4, h5 = st.columns([2, 1.2, 1.5, 1.5, 1.2])
        h1.markdown("**Index**")
        h2.markdown("**% Thay đổi**")
        h3.markdown("**GTGD hôm nay**")
        h4.markdown("**GTGD 5 phiên trước**")
        h5.markdown("**Tỷ lệ GTGD**")

        for g in groups:
            r1, r2, r3, r4, r5 = st.columns([2, 1.2, 1.5, 1.5, 1.2])
            chg = g.get("change_pct", 0) or 0
            chg_color = "green" if chg > 0 else "red" if chg < 0 else "gray"
            ratio = g.get("value_ratio", 100) or 100
            ratio_color = "green" if ratio > 100 else "red" if ratio < 80 else "gray"

            r1.markdown(f"**{g.get('name', '—')}**")
            r2.markdown(f":{chg_color}[{chg:+.2f}%]")
            r3.markdown(f"{g.get('value_today', 0):,.0f} tỷ")
            r4.markdown(f"{g.get('value_5d_ago', 0):,.0f} tỷ")
            r5.markdown(f":{ratio_color}[{ratio:.2f}%]")

    # Trong phần hiển thị Bảng 2 Breadth, thêm row phân tích sàn:
    st.markdown("##### 📊 Phân tích theo sàn")

    ex_data = breadth_full.get("by_exchange", {})
    cols_ex = st.columns(3)
    for i, ex in enumerate(["HOSE", "HNX", "UPCOM"]):
        with cols_ex[i]:
            if ex in ex_data:
                d = ex_data[ex]
                emoji = "🟢" if d["ad_ratio"] > 1.5 and d["avg_chg"] > 0 else \
                        "🔴" if d["ad_ratio"] < 0.7 or d["avg_chg"] < -0.5 else "🟡"
                st.metric(
                    f"{emoji} {ex}",
                    f"{d['advance']}▲ / {d['decline']}▼",
                    delta=f"{d['avg_chg']:+.2f}%",
                    delta_color="normal"
                )
            else:
                st.metric(ex, "—", "—")
# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU
# ==========================================
@st.fragment
def render_screener_fragment():
    st.subheader(f"Danh Sách Quét Sàn {exchange_choice}")
    scan_button = st.button("🚀 KÍCH HOẠT QUÉT TOÀN DIỆN", use_container_width=True, type="primary")

    if scan_button:
        ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice

        tickers = get_all_tickers(ex_code)

        if tickers is None or len(tickers) == 0:
            st.error("⚠️ Lỗi từ data_loader.py: Hàm `get_all_tickers` trả về danh sách rỗng!")
        else:
            ref_range = {
                "HOSE": "~400-430 mã", "HNX": "~300 mã", "UPCOM": "~900 mã", "Tất cả 3 sàn": "~1500-1600 mã",
            }.get(exchange_choice, "")
            st.info(f"📊 Hệ thống đã lấy thành công danh sách **{len(tickers)}** mã từ API "
                    f"(sàn **{exchange_choice}**, chuẩn thực tế khoảng {ref_range}).")

            ticker_set = set(tickers)
            priority_present = [t for t in PRIORITY_TICKERS if t in ticker_set]
            rest = [t for t in tickers if t not in set(priority_present)]

            if fast_mode:
                tickers_ordered = priority_present if priority_present else tickers
                st.caption(f"⚡ Chế độ NHANH đang bật: chỉ quét {len(tickers_ordered)} mã vốn hoá lớn/thanh khoản cao.")
            else:
                tickers_ordered = priority_present + rest
                extra_scanned = max(0, max_scan - len(priority_present))
                if extra_scanned < len(rest) * 0.3:
                    st.warning(
                        f"⚠️ Chế độ NHANH đã tắt, nhưng \"Số lượng mã quét tối đa\" đang chỉ để **{max_scan}** "
                        f"-> chỉ quét thêm được **{extra_scanned} mã** ngoài {len(priority_present)} mã ưu tiên. "
                        "**Hãy kéo thanh trượt \"Số lượng mã quét tối đa\" ở sidebar lên vài trăm — 1500+**."
                    )

            tickers_to_scan = tickers_ordered[:max_scan]

            rate_per_min = 60 if active_api_key else 20
            eta_min = len(tickers_to_scan) / rate_per_min
            st.caption(
                f"⏱️ Ước tính thời gian quét: khoảng **{eta_min:.1f} phút** "
                f"(giới hạn {rate_per_min} request/phút{' - đã dùng API key' if active_api_key else ' - tài khoản khách'})."
            )

            scan_start_time = time.time()
            hard_timeout = max(240, min(1200, eta_min * 60 * 3))

            live_results_box = st.empty()

            with st.status(f"Đang quét {len(tickers_to_scan)} mã... (ước tính ~{eta_min:.1f} phút)", expanded=True) as status:
                progress_bar = st.progress(0)
                results = []
                error_logs = []
                total = len(tickers_to_scan)
                processed = 0
                timed_out = False

                def process_ticker(ticker):
                    if ticker in BLACKLIST:
                        return {"status": "skip"}
                    try:
                        df = get_stock_data(ticker, days_back=300)
                        if df is None or df.empty:
                            return {"status": "error", "msg": f"{ticker}: get_stock_data trả về None/Empty."}
                        try:
                            res = calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
                            if res is None:
                                return {"status": "error", "msg": f"{ticker}: calculate_technical_signals trả về None."}
                            return {"status": "success", "data": res}
                        except Exception as e:
                            return {"status": "error", "msg": f"{ticker}: Lỗi indicators.py -> {str(e)}"}
                    except Exception as e:
                        return {"status": "error", "msg": f"{ticker}: Lỗi data_loader.py -> {str(e)}"}

                max_workers = 4
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_ticker = {executor.submit(process_ticker, t): t for t in tickers_to_scan}

                    try:
                        pending = set(future_to_ticker.keys())
                        while pending:
                            remaining_time = hard_timeout - (time.time() - scan_start_time)
                            if remaining_time <= 0:
                                raise concurrent.futures.TimeoutError()

                            done_now, pending = concurrent.futures.wait(
                                pending, timeout=min(3, remaining_time),
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
                                except Exception as e:
                                    error_logs.append(f"Lỗi luồng ThreadPool: {str(e)}")

                            elapsed = time.time() - scan_start_time
                            status.update(label=(
                                f"Đang quét... {processed}/{total} mã | "
                                f"✅ {len(results)} hợp lệ | ⏱️ {elapsed:.0f}s trôi qua"
                            ))
                            progress_bar.progress(min(processed / total, 1.0))

                            if done_now and results:
                                preview_df = pd.DataFrame(results)
                                if signal_filter != "Tất cả" and 'Trạng thái' in preview_df.columns:
                                    preview_df_show = preview_df[preview_df['Trạng thái'] == signal_filter]
                                else:
                                    preview_df_show = preview_df
                                live_cols = [c for c in [
                                    "Mã CP", "Giá", "GTGD (Tỷ)", "Vol x TB20",
                                    "Dòng Tiền", "Xu Hướng", "Định Giá (129)", "Trạng thái",
                                ] if c in preview_df_show.columns]
                                preview_df_live = preview_df_show[live_cols] if live_cols else preview_df_show
                                with live_results_box.container():
                                    st.caption(
                                        f"📊 Kết quả LIVE (đang cập nhật): {len(preview_df_live)} mã — "
                                        "bảng đầy đủ sẽ có ở tab 📊 Kết Quả Quét sau khi quét xong."
                                    )
                                    st.dataframe(preview_df_live, use_container_width=True, hide_index=True)
                    except concurrent.futures.TimeoutError:
                        timed_out = True
                        executor.shutdown(wait=False, cancel_futures=True)

                if timed_out:
                    status.update(
                        label=f"⏳ Đã dừng do quá thời gian ({hard_timeout/60:.0f} phút) — hiển thị {len(results)} mã ({processed}/{total}).",
                        state="complete", expanded=False
                    )
                elif len(results) > 0:
                    status.update(label=f"✅ Quét xong {len(results)} mã hợp lệ!", state="complete", expanded=False)
                else:
                    status.update(label=f"❌ Quét thất bại toàn bộ!", state="error", expanded=True)

            live_results_box.empty()

            if timed_out:
                st.warning(
                    f"⏳ Đã dừng quét sau {hard_timeout/60:.0f} phút (mới xử lý {processed}/{total} mã). "
                    "Muốn quét hết, hãy giảm 'Số lượng mã quét tối đa' hoặc thêm API key vnstock."
                )

            if len(error_logs) > 0 and len(results) == 0:
                st.error("🚨 APP BỊ KẸT VÌ CÁC LỖI DƯỚI ĐÂY:")
                with st.expander("MỞ RỘNG ĐỂ XEM CHI TIẾT LỖI NGẦM", expanded=True):
                    for err in error_logs[:10]:
                        st.code(err)
                    if len(error_logs) > 10:
                        st.write(f"... và {len(error_logs) - 10} mã khác bị lỗi y hệt.")

            st.session_state['scan_results'] = results
            st.rerun()

    if not st.session_state.get('scan_results', []):
        st.caption("Hãy cấu hình thông số ở Sidebar trái và bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' để bắt đầu. "
                    "Kết quả sau khi quét xong sẽ hiển thị ở tab **📊 Kết Quả Quét**.")
    else:
        n_found = len(st.session_state['scan_results'])
        st.success(f"✅ Đã có {n_found} mã trong kết quả quét gần nhất. "
                    "👉 Chuyển sang tab **📊 Kết Quả Quét** ở trên để xem bảng chi tiết.")


with tab_screener:
    render_screener_fragment()

# ==========================================
# TAB 3: KẾT QUẢ QUÉT
# ==========================================
with tab_results:
    st.subheader("📊 Kết Quả Quét")
    if st.session_state.get('scan_results', []):
        raw_df = pd.DataFrame(st.session_state['scan_results'])
        df_display = render_search_and_export(raw_df)
        st.session_state['df_display_cached'] = df_display
        render_screener_results(df_display, signal_filter)
    else:
        st.info("Chưa có dữ liệu quét. Sang tab **🔍 Bộ Lọc** để bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' trước.")

# ==========================================
# TAB 4: TÍN HIỆU & CẢNH BÁO
# ==========================================
with tab_signals:
    st.subheader("📡 Tín Hiệu & Cảnh Báo")
    df_display_cached = st.session_state.get('df_display_cached')
    if isinstance(df_display_cached, pd.DataFrame) and not df_display_cached.empty:
        render_screener_signals(df_display_cached, signal_filter)
    else:
        st.info("Chưa có dữ liệu quét. Sang tab **🔍 Bộ Lọc** để quét, rồi ghé tab **📊 Kết Quả Quét** trước.")

# ==========================================
# TAB 5: MÔ PHỎNG XU HƯỚNG
# ==========================================
with tab_simulation:
    st.subheader("🔮 Mô Phỏng Xu Hướng — Kijun17 / Knife65 / Knife2-129")
    st.caption(
        "Mục đích tab này: mô phỏng ĐÚNG state machine Tăng → Sideway → Giảm theo tài liệu "
        "(3 đường cùng hướng, Chikou span, hợp bích, không mua đuổi, xác nhận khối lượng)."
    )

    sim_ticker = st.text_input("Nhập mã cổ phiếu (Gõ xong nhấn Enter):", value="HPG", key="sim_ticker_input").upper().strip()

    if sim_ticker:
        with st.spinner(f"Đang xử lý dữ liệu {sim_ticker}..."):
            df_sim = get_stock_data(sim_ticker, days_back=500)

            if df_sim is not None and not df_sim.empty:
                df_sim.columns = [str(c).lower().strip() for c in df_sim.columns]
                eng = te.compute_fairy_engine(df_sim)

                if eng is None:
                    st.warning(
                        f"⚠️ Mã {sim_ticker} chưa đủ lịch sử (cần tối thiểu ~156 phiên giao dịch) "
                        "để tính đường Knife2-129. Hãy thử mã có thời gian niêm yết lâu hơn."
                    )
                else:
                    snap_sim = te.get_latest_snapshot(eng)

                    xh = snap_sim['xu_huong']
                    xh_display = {"Tăng": "🟢 Tăng", "Giảm": "🔴 Giảm", "Sideway": "🟡 Sideway"}.get(xh, xh)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Xu Hướng Hiện Tại", xh_display)
                    c2.metric("Cách Knife2-129", f"{snap_sim['pct_vs_129']}%" if snap_sim['pct_vs_129'] is not None else "—")
                    c3.metric("Vol / TB20", f"{snap_sim['v_ratio']}x" if snap_sim['v_ratio'] is not None else "—")
                    c4.metric("Hợp Bích (65≈129)", "✅ Có" if snap_sim['hop_bich'] else "—")

                    badges = []
                    if snap_sim['khong_mua_duoi']:
                        badges.append("🟢 Còn trong vùng KHÔNG MUA ĐUỔI (giá mới vừa vượt mây)")
                    if snap_sim['canh_bao_mua_duoi']:
                        badges.append("⚠️ CẢNH BÁO MUA ĐUỔI — giá đã đi xa mây, rủi ro mua bằng lòng tham")
                    if snap_sim['cau_truc_khoe']:
                        badges.append("💪 Cấu trúc khoẻ: đỉnh sau cao hơn đỉnh trước, đáy sau cao hơn đáy trước")
                    if snap_sim['canh_bao_tao_dinh']:
                        badges.append("⚠️ CẢNH BÁO TẠO ĐỈNH — giá gần đỉnh nhưng thanh khoản kiệt dần")
                    if snap_sim['vung_phan_phoi']:
                        badges.append("🚨 VÙNG PHÂN PHỐI — volume đột biến tại đỉnh + giá vượt xa 129 (~30%+)")
                    if badges:
                        st.info("  \n".join(badges))

                    plot_df = eng.tail(180).copy()
                    if 'time' in plot_df.columns:
                        plot_df['Ngay'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
                        plot_df.set_index('Ngay', inplace=True)

                    import plotly.graph_objects as go
                    from plotly.subplots import make_subplots

                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                        vertical_spacing=0.03, row_heights=[0.8, 0.2])

                    trend_color = {"Tăng": "rgba(0, 200, 83, 0.08)", "Giảm": "rgba(255, 23, 68, 0.08)", "Sideway": None}
                    seg_start = 0
                    xh_series = plot_df['Xu_Huong'].tolist()
                    idx_list = plot_df.index.tolist()
                    for i in range(1, len(xh_series) + 1):
                        if i == len(xh_series) or xh_series[i] != xh_series[seg_start]:
                            color = trend_color.get(xh_series[seg_start])
                            if color:
                                fig.add_vrect(x0=idx_list[seg_start], x1=idx_list[i - 1],
                                              fillcolor=color, line_width=0, row=1, col=1)
                            seg_start = i

                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['close'],
                                             line=dict(color='#e5e0f7', width=2), name='Giá Đóng Cửa'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['knife65'],
                                             line=dict(color='rgba(0, 200, 83, 0.5)', width=1), name='Knife1 (65)'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['knife129'],
                                             line=dict(color='rgba(255, 23, 68, 0.5)', width=1.5),
                                             fill='tonexty', fillcolor='rgba(128, 128, 128, 0.15)', name='Knife2 (129) — Mây'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['kijun17'],
                                             line=dict(color='#2962FF', width=1.5), name='Kijun (17)'), row=1, col=1)

                    chan_song = plot_df[plot_df['xac_nhan_chan_song']]
                    fig.add_trace(go.Scatter(x=chan_song.index, y=chan_song['close'] * 0.97,
                                             mode='markers', marker=dict(symbol='triangle-up', size=14, color='lime'),
                                             name='🎯 Chân Sóng (Vol xác nhận)'), row=1, col=1)

                    hop_bich_pts = plot_df[plot_df['hop_bich']]
                    fig.add_trace(go.Scatter(x=hop_bich_pts.index, y=hop_bich_pts['knife129'],
                                             mode='markers', marker=dict(symbol='diamond', size=6, color='#FFD700'),
                                             name='💎 Hợp Bích (65≈129)'), row=1, col=1)

                    khong_duoi_pts = plot_df[plot_df['khong_mua_duoi']]
                    fig.add_trace(go.Scatter(x=khong_duoi_pts.index, y=khong_duoi_pts['close'],
                                             mode='markers', marker=dict(symbol='circle', size=5, color='#00E5FF'),
                                             name='✅ Vùng Không Mua Đuổi'), row=1, col=1)

                    dinh_pts = plot_df[plot_df['canh_bao_tao_dinh'] | plot_df['vung_phan_phoi']]
                    fig.add_trace(go.Scatter(x=dinh_pts.index, y=dinh_pts['close'] * 1.02,
                                             mode='markers', marker=dict(symbol='x', size=10, color='orange'),
                                             name='⚠️ Cảnh Báo Đỉnh/Phân Phối'), row=1, col=1)

                    start_up = plot_df[plot_df['trend_start'] & (plot_df['Xu_Huong'] == 'Tăng')]
                    start_dn = plot_df[plot_df['trend_start'] & (plot_df['Xu_Huong'] == 'Giảm')]
                    fig.add_trace(go.Scatter(x=start_up.index, y=start_up['close'] * 0.95,
                                             mode='markers', marker=dict(symbol='star', size=13, color='#00C853'),
                                             name='🟢 Bắt Đầu Tăng'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=start_dn.index, y=start_dn['close'] * 1.05,
                                             mode='markers', marker=dict(symbol='star', size=13, color='#FF1744'),
                                             name='🔴 Bắt Đầu Giảm'), row=1, col=1)

                    colors = ['#00C853' if row['close'] >= row['open'] else '#FF1744' for _, row in plot_df.iterrows()]
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['volume'], marker_color=colors, name='Volume'), row=2, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['vol_ma20'],
                                             line=dict(color='#FF6D00', width=2), name='Volume MA20'), row=2, col=1)

                    fig.update_layout(
                        title=f"<b>Mô Phỏng Xu Hướng Cô Tiên: {sim_ticker}</b>",
                        height=760, margin=dict(l=10, r=160, t=40, b=10),
                        showlegend=True,
                        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01,
                                    font=dict(size=11), bgcolor='rgba(0,0,0,0)'),
                        xaxis_rangeslider_visible=False, dragmode='pan',
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#dcd6ec')
                    )
                    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("📖 Chú giải các ký hiệu trên biểu đồ"):
                        st.markdown(
                            "- **Nền xanh/đỏ mờ**: giai đoạn Xu Hướng Tăng/Giảm đang được state machine ghi nhận.\n"
                            "- **⭐ Bắt Đầu Tăng/Giảm**: phiên đầu tiên hệ thống xác nhận đổi xu hướng.\n"
                            "- **🎯 Chân Sóng**: phiên bắt đầu Tăng có khối lượng xác nhận (≥1.75x MA20).\n"
                            "- **💎 Hợp Bích**: Knife1(65) và Knife2(129) hội tụ sát nhau (≤0.14%).\n"
                            "- **✅ Vùng Không Mua Đuổi**: đang Tăng và giá chỉ vừa vượt mây (≤3%).\n"
                            "- **⚠️ Cảnh Báo Đỉnh/Phân Phối**: giá gần đỉnh nhưng thanh khoản kiệt, hoặc volume đột biến tại đỉnh."
                        )
            else:
                st.warning(f"⚠️ Không có dữ liệu cho mã {sim_ticker}. Hãy kiểm tra lại mã cổ phiếu!")

# ==========================================
# TAB 6: BACKTEST
# ==========================================
with tab_backtest:
    st.subheader("🛠️ Hệ Thống Backtest Dài Hạn (Khung 1DAY)")
    st.caption("Thuật toán Quant: Tự động bắt Râu nến để Stoploss (-7%) hoặc Take Profit (+15%). Chặn bán nếu gãy trend Kumo.")

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        ticker_bt = st.text_input("Nhập mã cổ phiếu để test (Ví dụ: FPT, HPG):", value="FPT", key="bt_ticker").upper()
    with col_input2:
        years_back = st.slider("Số NĂM quá khứ muốn kiểm tra:", min_value=1, max_value=10, value=5)

    if st.button("🚀 Bắt đầu chạy Backtest Tự Động"):
        with st.spinner(f"Đang cào dữ liệu Daily trong {years_back} năm và mô phỏng giao dịch mã {ticker_bt}..."):
            df_daily = bt.get_daily_data(ticker_bt, years_back)

            if df_daily is not None and not df_daily.empty:
                df_ichimoku = bt.calculate_ichimoku_daily(df_daily)

                if df_ichimoku is not None:
                    stats, trade_log = bt.run_ichimoku_backtest_daily(df_ichimoku)

                    st.success(f"Dữ liệu kiểm thử mã {ticker_bt} trong {years_back} năm thành công!")

                    st.subheader("📊 Kết quả hiệu suất chiến lược")
                    m_col1, m_col2, m_col3 = st.columns(3)
                    m_col1.metric("Vốn cuối kỳ", stats["Vốn cuối kỳ"])
                    m_col2.metric("Lợi nhuận ròng", stats["Lợi nhuận ròng"])
                    m_col3.metric("Tỷ lệ Thắng (Win Rate)", stats["Tỷ lệ Thắng (Win Rate)"])

                    st.subheader("📋 Nhật ký lệnh chi tiết của Bot")
                    st.dataframe(trade_log, use_container_width=True)
                else:
                    st.error("Dữ liệu quá ngắn, không đủ để tính toán đám mây Ichimoku!")
            else:
                st.error("Lỗi: Không lấy được dữ liệu. Hãy kiểm tra lại mã cổ phiếu hoặc API đang bảo trì!")

# ==========================================
# TAB 7: BÁO CÁO CTCK
# ==========================================
import requests as _req
import pandas as _pd
from datetime import datetime as _dt, timedelta as _td

@st.cache_data(ttl=3600, show_spinner=False)
def _load_reports_json() -> dict:
    import requests as _r
    try:
        base = st.secrets.get("GITHUB_RAW_BASE", "").rstrip("/")
    except Exception:
        base = ""
    if not base:
        base = "https://raw.githubusercontent.com/nnnhutien-cpu/Fairy-stock/main"

    url = f"{base}/reports.json"
    try:
        resp = _r.get(url, timeout=10)
        resp.encoding = "utf-8"
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}", "data": []}
    except Exception as e:
        return {"error": str(e), "data": []}


with tab_reports:
    st.subheader("📑 Hệ Thống Báo Cáo Định Giá Cổ Phiếu")
    st.caption(
        "Dữ liệu tổng hợp tự động từ **DNSE · Vietstock · CafeF** — "
        "bot cập nhật 2 lần/ngày (10:00 SA & 15:30 CH)."
    )

    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        filter_action = st.selectbox(
            "Lọc Khuyến Nghị:",
            ["Tất cả", "MUA", "NẮM GIỮ", "BÁN", "TÍCH LŨY", "KHẢ QUAN"],
        )
    with col_f2:
        filter_source = st.selectbox(
            "Nguồn dữ liệu:",
            ["Tất cả", "DNSE", "DNSE Research", "Vietstock", "CafeF"],
        )
    with col_f3:
        rep_ticker = st.text_input(
            "Mã cổ phiếu (để trống = toàn thị trường):",
            value="", key="rep_ticker_v5",
            placeholder="Ví dụ: FPT, HPG, VNM...",
        ).upper().strip()

    col_btn, col_note = st.columns([1, 4])
    with col_btn:
        force_refresh = st.button("🔄 Làm mới", key="refresh_reports_v5")

    if force_refresh:
        _load_reports_json.clear()

    with st.spinner("Đang tải dữ liệu báo cáo..."):
        payload = _load_reports_json()

    if "error" in payload and not payload.get("data"):
        st.error(
            f"⚠️ Không tải được reports.json: `{payload['error']}`\n\n"
            "**Kiểm tra:**\n"
            "1. File `reports.json` đã có trong repo chưa? "
            "Vào GitHub → Actions → chạy thủ công workflow **Scrape Analyst Reports**.\n"
            "2. Repo có public không? Nếu private cần thêm token vào secrets.\n"
        )
        st.stop()

    updated_at = payload.get("updated_at", "")
    raw_data   = payload.get("data", [])

    with col_note:
        st.caption(f"⏱️ Dữ liệu cập nhật lần cuối: **{updated_at}** — {len(raw_data)} báo cáo")

    df_all = pd.DataFrame(raw_data)

    if df_all.empty:
        st.info(
            "Kho báo cáo hiện đang trống.\n\n"
            "Vào **GitHub → Actions → Scrape Analyst Reports → Run workflow** "
            "để bot cào dữ liệu về ngay."
        )
        st.stop()

    for col in ["buy_price", "target_price"]:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(
                df_all[col].astype(str).str.replace(",", "").str.replace(".", ""),
                errors="coerce"
            ).fillna(0)

    mask = (df_all["buy_price"] > 0) & (df_all["target_price"] > 0)
    df_all["upside_pct"] = 0.0
    df_all.loc[mask, "upside_pct"] = (
        (df_all.loc[mask, "target_price"] - df_all.loc[mask, "buy_price"])
        / df_all.loc[mask, "buy_price"] * 100
    ).round(1)

    df_show = df_all.copy()
    if rep_ticker:
        df_show = df_show[df_show["ticker"].str.upper() == rep_ticker]
    if filter_action != "Tất cả":
        df_show = df_show[
            df_show["action"].str.upper().str.contains(filter_action, na=False)
        ]
    if filter_source != "Tất cả":
        df_show = df_show[df_show["source"] == filter_source]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📋 Tổng báo cáo", len(df_show))
    n_buy  = df_show["action"].str.upper().str.contains("MUA|TÍCH LŨY|KHẢ QUAN|BUY", na=False).sum()
    n_hold = df_show["action"].str.upper().str.contains("GIỮ|HOLD|NEUTRAL", na=False).sum()
    n_sell = df_show["action"].str.upper().str.contains("BÁN|SELL", na=False).sum()
    m2.metric("🟢 Mua / Tích lũy", int(n_buy))
    m3.metric("🟡 Nắm giữ", int(n_hold))
    m4.metric("🔴 Bán", int(n_sell))

    st.divider()

    if df_show.empty:
        st.warning("Không có báo cáo nào khớp bộ lọc.")
    else:
        st.dataframe(
            df_show[["date", "ticker", "company", "action",
                     "buy_price", "target_price", "upside_pct",
                     "source", "report_url"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "date":         st.column_config.TextColumn("📅 Ngày"),
                "ticker":       st.column_config.TextColumn("🏷️ Mã"),
                "company":      st.column_config.TextColumn("🏢 CTCK"),
                "action":       st.column_config.TextColumn("⚡ Khuyến Nghị"),
                "buy_price":    st.column_config.NumberColumn("💰 Giá Khuyến Nghị", format="%d ₫"),
                "target_price": st.column_config.NumberColumn("🎯 Giá Mục Tiêu",    format="%d ₫"),
                "upside_pct":   st.column_config.NumberColumn("🚀 Upside",          format="%.1f %%"),
                "source":       st.column_config.TextColumn("🔗 Nguồn"),
                "report_url":   st.column_config.LinkColumn("📥 Báo Cáo", display_text="Xem"),
            },
        )

        csv_bytes = df_show.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Tải CSV",
            data=csv_bytes,
            file_name=f"bao_cao_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

# ==========================================
# TAB 8: CHIẾN LƯỢC TÍCH LŨY
# ==========================================
with tab_accum:
    render_accumulation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift)
