import streamlit as st
import pandas as pd
import concurrent.futures
import time
import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
from supabase import create_client
import traceback
from datetime import datetime

from indicators import market_snapshot
from trend_engine import market_recommendation
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex, set_rate_limit
from indicators import calculate_technical_signals
import trend_engine as te
from ui_layout import render_sidebar, render_market_tab, render_screener_results, render_screener_signals
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt
import valuation
from market_breadth import get_market_breadth, render_breadth_panel
from tab_khuyen_nghi import render_recommendation_tab
from screener_suc_bat import render_suc_bat_tab

# ✅ THÊM IMPORT MỚI - DANH MỤC
from tab_portfolio_v2 import render_portfolio_v2_tab 

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Cô Tiên Stock", layout="wide", initial_sidebar_state="expanded")

# --- 1b. GIAO DIỆN: TÍM ĐẬM SANG TRỌNG + FONT + HÒA HEADER ---
# Bộ class dùng chung (sb-header, lk-card, badge-*, ...) — cùng bộ token màu
# với tab "Sức Bật" / "Danh mục" để mọi tab trong app đồng bộ 1 ngôn ngữ đồ hoạ.
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

    /* ══════════ Bộ class dùng chung mọi tab (đồng bộ với Sức Bật / Danh mục) ══════════ */
    .sb-header {
        background: linear-gradient(135deg,#1a1a2e,#16213e);
        border-radius: 12px; padding: 16px 20px; margin-bottom: 18px;
    }
    .sb-title { font-size: 22px; font-weight: 800; color: #e0e0ff; }
    .sb-sub   { font-size: 12px; color: #888; margin-top: 2px; }
    .sb-note {
        background: #1a1a2e; border-left: 3px solid #8b7fb5;
        padding: 10px 14px; border-radius: 0 8px 8px 0;
        font-size: 12px; color: #aaa; margin-bottom: 14px;
    }
    .lk-card {
        background: #1e1e2e; border: 1px solid #2c2151;
        border-radius: 14px; padding: 20px 24px; margin-bottom: 16px;
    }
    .lk-ticker { font-size: 28px; font-weight: 800; color: #a78bfa; letter-spacing: 2px; }
    .lk-company { font-size: 13px; color: #888; margin-top: 2px; margin-bottom: 16px; }
    .lk-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 14px; }
    .lk-metric { background: #12102a; border-radius: 10px; padding: 12px 14px; }
    .lk-label { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: .5px; }
    .lk-value { font-size: 22px; font-weight: 700; color: #e0e0ff; margin-top: 3px; }
    .lk-sub   { font-size: 10px; color: #555; margin-top: 2px; }
    .val-up   { color: #00e676 !important; }
    .val-down { color: #ff5252 !important; }
    .val-warn { color: #ffd740 !important; }
    .lk-section { font-size: 11px; color: #8b7fb5; text-transform: uppercase;
                   letter-spacing: .6px; margin: 14px 0 8px;
                   border-bottom: 1px solid #2c2151; padding-bottom: 4px; }
    .sr-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .sr-table th { color: #666; font-weight: 400; text-align: left;
                   padding: 4px 8px; font-size: 11px; text-transform: uppercase; }
    .sr-table td { padding: 5px 8px; border-bottom: 1px solid #1e1a33; color: #ccc; }
    .sr-table tr:last-child td { border-bottom: none; }
    .badge-r { background:#3a1a1a; color:#ff5252; padding:2px 8px;
               border-radius:4px; font-size:11px; font-weight:600; }
    .badge-s { background:#1a3a1a; color:#00e676; padding:2px 8px;
               border-radius:4px; font-size:11px; font-weight:600; }
    .badge-fib { background:#1a1a3a; color:#7c9ef5; padding:2px 6px;
                 border-radius:4px; font-size:10px; }
    .formula-note {
        background: #12102a; border-left: 3px solid #a78bfa;
        padding: 10px 14px; border-radius: 0 8px 8px 0;
        font-size: 12px; color: #999; margin-top: 12px; line-height: 1.7;
    }
    .sb-stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
    .sb-stat { background: #1e1e2e; border-radius: 10px; padding: 10px 16px;
               flex: 1; min-width: 130px; }
    .sb-stat-label { font-size: 11px; color: #888; text-transform: uppercase; }
    .sb-stat-value { font-size: 20px; font-weight: 800; color: #e0e0ff; margin-top: 2px; }
    .src-badge { display:inline-block; padding:1px 7px; border-radius:10px;
                 font-size:10px; font-weight:600; margin-left:6px; }
    .src-vci     { background:#1a2a3a; color:#5b9bd5; }
    .src-fireant { background:#1a2e1a; color:#4caf50; }
    .src-yahoo   { background:#1a1a3a; color:#8b7fb5; }
</style>
""", unsafe_allow_html=True)


def sb_header(title: str, subtitle: str = "") -> None:
    """Header đồng bộ đồ họa cho mọi tab (thay cho st.subheader / st.markdown('###'))."""
    sub_html = f'<div class="sb-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div class="sb-header">
        <div class="sb-title">{title}</div>
        {sub_html}
    </div>
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

# --- 4. TẠO 8 TAB (THÊM TAB QUẢN LÝ GIAO DỊCH) ---
# Đã bỏ tab "📑 Báo Cáo" (gọi reports.json qua mạng mỗi lần render, làm chậm
# tải trang) để web load nhanh hơn — các tab còn lại không phụ thuộc vào nó.
tab_market, tab_screener, tab_results, tab_signals, tab_recommendation, tab_suc_bat, tab_portfolio = st.tabs([
    "🌟 Thị Trường",
    "🔍 Bộ Lọc",
    "📊 Kết Quả Quét",
    "📡 Tín Hiệu & Cảnh Báo",
    "💡 Khuyến Nghị",
    "🚀 Sức Bật",
    "💼 Danh mục",
])

# ==========================================
# TAB 1: THỊ TRƯỜNG CHUNG
# ==========================================

with tab_market:
    col_title, col_btn, col_interval = st.columns([3, 1, 1])
    with col_title:
        sb_header("🌟 Tổng quan thị trường real-time")
    with col_interval:
        refresh_interval = st.selectbox(
            "⏱️ Tự làm mới",
            options=[0, 30, 60, 120, 300],
            format_func=lambda x: "Tắt" if x == 0 else f"{x}s",
            index=2,
            key="refresh_interval_select",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("🔄 CẬP NHẬT DỮ LIỆU", type="primary", use_container_width=True):
            try: get_intraday_vnindex.clear()
            except Exception: pass
            try: get_vnindex_data.clear()
            except Exception: pass
            try: market_snapshot.clear()
            except Exception: pass
            try: get_market_breadth.clear()
            except Exception: pass
            st.rerun()

    if refresh_interval > 0:
        import streamlit.components.v1 as _components
        _components.html(
            f"""
            <script>
                setTimeout(function() {{
                    const buttons = window.parent.document.querySelectorAll('button[kind="primary"]');
                    for (const btn of buttons) {{
                        if (btn.innerText.includes('CẬP NHẬT')) {{
                            btn.click();
                            break;
                        }}
                    }}
                }}, {refresh_interval * 1000});
            </script>
            """,
            height=0,
        )
        st.caption(f"🔁 Tự động làm mới mỗi **{refresh_interval}s**")

    st.divider()

    snap = {}
    snap_error = None
    pe_stats_data = None
    pe_hist = None
    breadth = None
    reco = None
    try:
        snap = market_snapshot(symbol="VNINDEX", days=250) or {}
    except Exception as e:
        snap_error = str(e)
    try:
        _price = snap.get("price") or 0
        pe_now_val = valuation.get_current_pe(_price if _price > 0 else None)
        pe_hist    = valuation.get_pe_history(years=20)
        pe_stats_data = valuation.pe_stats(pe_hist, pe_now_val)
    except Exception:
        pass
    try:
        breadth = get_market_breadth()
    except Exception:
        pass
    try:
        reco = market_recommendation(snap, pe_stats=pe_stats_data)
    except Exception:
        pass

    intraday_df = get_intraday_vnindex()
    chart_df, df_today = None, None
    current_index = 0

    if intraday_df is not None and not intraday_df.empty:
        col_mapping = {}
        for col in intraday_df.columns:
            lc = str(col).lower().strip()
            if lc in ['close', 'price', 'c', 'điểm', 'index', 'indexvalue']:
                col_mapping[col] = 'close'
            elif lc in ['volume', 'vol', 'v', 'khối lượng', 'matchvolume']:
                col_mapping[col] = 'volume'
            elif lc in ['time', 't', 'thời gian']:
                col_mapping[col] = 'time'
        intraday_df.rename(columns=col_mapping, inplace=True)

        if 'time' in intraday_df.columns and 'close' in intraday_df.columns:
            intraday_df['close']  = pd.to_numeric(intraday_df['close'], errors='coerce').fillna(0)
            intraday_df['volume'] = pd.to_numeric(
                intraday_df['volume'] if 'volume' in intraday_df.columns else 0,
                errors='coerce'
            ).fillna(0)
            intraday_df['time']     = pd.to_datetime(intraday_df['time'])
            intraday_df['hour_min'] = intraday_df['time'].dt.strftime('%H:%M')
            intraday_df['date']     = intraday_df['time'].dt.date

            unique_dates = sorted(intraday_df['date'].unique())
            latest_date  = unique_dates[-1] if unique_dates else None
            prev_date    = unique_dates[-2] if len(unique_dates) >= 2 else None

            df_today = intraday_df[
                (intraday_df['date'] == latest_date) &
                (intraday_df['hour_min'] >= '09:00') &
                (intraday_df['hour_min'] <= '15:00')
            ].copy()

            df_yesterday = intraday_df[
                (intraday_df['date'] == prev_date) &
                (intraday_df['hour_min'] >= '09:00') &
                (intraday_df['hour_min'] <= '15:00')
            ].copy() if prev_date else pd.DataFrame(columns=intraday_df.columns)

            if not df_yesterday.empty:
                df_yesterday['Vol_Hôm_Qua'] = df_yesterday['volume'].cumsum()
                prev_vol = df_yesterday['Vol_Hôm_Qua'].iloc[-1]
            else:
                prev_vol = 0

            if not df_today.empty:
                df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
                current_index   = df_today['close'].iloc[-1]
                current_vol     = df_today['Vol_Hôm_Nay'].iloc[-1]
                max_time_actual = df_today['hour_min'].max()

                vol_change = current_vol - prev_vol

                m1, m2, m3 = st.columns(3)
                m1.metric("📊 VN-INDEX",                f"{current_index:,.2f}")
                m2.metric("💰 Thanh khoản hôm nay",      f"{current_vol/1e6:,.1f}M CP",
                          f"{vol_change/1e6:+,.1f}M CP so với cùng giờ hôm qua" if prev_vol else None)
                m3.metric("⏳ Thanh khoản hôm qua (EOD)", f"{prev_vol/1e6:,.1f}M CP")
                st.info(f"🕒 Dữ liệu thực tế đến **{max_time_actual}** (trễ ~1 phút)")

                times = (
                    pd.date_range("09:00", "11:30", freq="min").strftime('%H:%M').tolist() +
                    pd.date_range("13:00", "15:00", freq="min").strftime('%H:%M').tolist()
                )

                chart_today = (
                    pd.DataFrame({'hour_min': times})
                    .merge(
                        df_today.groupby('hour_min')['Vol_Hôm_Nay'].last().reset_index(),
                        on='hour_min', how='left'
                    )
                )
                chart_today['Vol_Hôm_Nay'] = chart_today['Vol_Hôm_Nay'].ffill()
                chart_today.loc[chart_today['hour_min'] > max_time_actual, 'Vol_Hôm_Nay'] = None
                chart_df = chart_today.set_index('hour_min')

                if not df_yesterday.empty:
                    yday_agg = (
                        pd.DataFrame({'hour_min': times})
                        .merge(
                            df_yesterday.groupby('hour_min')['Vol_Hôm_Qua'].last().reset_index(),
                            on='hour_min', how='left'
                        )
                    )
                    yday_agg['Vol_Hôm_Qua'] = yday_agg['Vol_Hôm_Qua'].ffill()
                    yday_agg = yday_agg.set_index('hour_min')
                    chart_df = chart_df.join(yday_agg, how='left')

    sb_header("💓 Nhịp đập thị trường")
    render_market_tab(chart_df, df_today)

    sb_header("🧠 Phân tích xu hướng")

    row1_l, row1_r = st.columns(2)

    with row1_l:
        with st.container(border=True):
            st.markdown("#### 📈 Xu hướng giá")

            trend_txt = snap.get("trend_text") or "—"
            ma20_txt  = snap.get("ma20_text")  or ""
            support   = snap.get("support")    or 0
            resist    = snap.get("resistance") or 0

            if snap_error and not snap.get("ma20"):
                st.caption(f"⚠️ {snap_error[:60]}")
            else:
                st.markdown(f"**{trend_txt}**")
                if ma20_txt and ma20_txt != "—":
                    st.caption(ma20_txt)

            ma_c1, ma_c2, ma_c3 = st.columns(3)
            ma_c1.metric("MA20",  f"{snap.get('ma20'):.1f}"  if snap.get('ma20')  else "—")
            ma_c2.metric("MA50",  f"{snap.get('ma50'):.1f}"  if snap.get('ma50')  else "—")
            ma_c3.metric("MA200", f"{snap.get('ma200'):.1f}" if snap.get('ma200') else "—")

            if support or resist:
                st.markdown(
                    f"**🟢 Hỗ trợ:** `{support:.1f}` "
                    f"&nbsp;•&nbsp; "
                    f"**🔴 Kháng cự:** `{resist:.1f}`"
                )

    with row1_r:
        with st.container(border=True):
            st.markdown("#### 💰 Định giá P/E (20 năm)")
            if pe_stats_data is None:
                st.info("⏳ Chưa tải được dữ liệu P/E")
            else:
                pe_c1, pe_c2 = st.columns(2)
                pe_c1.metric(
                    "P/E hiện tại",
                    f"{pe_stats_data['pe_now']:.1f}x" if pe_stats_data.get('pe_now') else "—",
                    delta=f"{pe_stats_data.get('pct_vs_avg', 0):+.1f}% vs TB"
                          if pe_stats_data.get('pct_vs_avg') else None,
                    delta_color="inverse"
                )
                pe_c2.metric(
                    "TB 20 năm",
                    f"{pe_stats_data['mean']:.1f}x" if pe_stats_data.get('mean') else "—",
                    delta=f"{pe_stats_data.get('zscore', 0):+.2f}σ"
                          if pe_stats_data.get('zscore') else None,
                )
                pct = pe_stats_data.get('percentile')
                if pct is not None:
                    color_pe = "🟢" if pct < 25 else "🟡" if pct < 75 else "🔴"
                    label_pe = "RẺ"  if pct < 25 else "HỢP LÝ" if pct < 75 else "ĐẮT"
                    st.progress(pct / 100, text=f"{color_pe} Percentile: {pct:.0f}% — {label_pe}")
                if pe_stats_data.get('comment'):
                    st.caption(pe_stats_data['comment'])
                if pe_hist is not None and not pe_hist.empty:
                    with st.expander("📈 P/E lịch sử 20 năm", expanded=False):
                        st.line_chart(pe_hist.set_index("date")["pe"], height=180)
                try:
                    src = valuation.get_current_pe_source()
                    if src:
                        st.caption(f"🔗 Nguồn: **{src}** — delay ~1 ngày GD")
                except Exception:
                    pass

    row2_l, row2_r = st.columns(2)

    with row2_l:
        with st.container(border=True):
            st.markdown("#### 📊 Chỉ báo kỹ thuật")

            rsi_val    = snap.get('rsi') or 50
            rsi_txt    = snap.get('rsi_text') or "—"
            macd_val   = snap.get('macd') or 0
            macd_sig   = snap.get('macd_signal') or 0
            macd_cross = snap.get('macd_cross') or "—"

            rsi_emoji = "🔴" if rsi_val >= 70 else ("🟢" if rsi_val <= 30 else "🟡")
            st.markdown(f"**RSI(14):** {rsi_emoji} `{rsi_val:.1f}` — {rsi_txt}")
            st.progress(min(rsi_val / 100, 1.0), text=f"RSI = {rsi_val:.1f}")
            st.divider()

            macd_emoji = "🟢" if macd_cross == "Vàng" else "🔴"
            macd_label = "Cắt lên (Vàng)" if macd_cross == "Vàng" else (
                         "Cắt xuống (Chết)" if macd_cross not in ["—", None] else "—")
            st.markdown(f"**MACD:** `{macd_val:.3f}` &nbsp;·&nbsp; **Signal:** `{macd_sig:.3f}`")
            if macd_cross not in ["—", None]:
                st.markdown(f"**Trạng thái:** {macd_emoji} {macd_label}")
            else:
                st.markdown("**Trạng thái:** —")

    with row2_r:
        with st.container(border=True):
            st.markdown("#### 🔊 Dòng tiền (Volume)")

            vol_today = snap.get('vol_today') or 0
            vol_avg   = snap.get('vol_avg')   or 0
            vol_ratio = snap.get('vol_ratio') or 0
            vol_txt   = snap.get('vol_text')  or "—"

            if vol_txt and vol_txt != "—":
                st.markdown(f"**{vol_txt}**")

            v1, v2 = st.columns(2)
            v1.metric("Vol phiên GD", f"{vol_today/1e6:,.1f}M" if vol_today else "—")
            v2.metric("TB 20 phiên",  f"{vol_avg/1e6:,.1f}M"   if vol_avg   else "—")

            if vol_ratio and vol_avg:
                st.progress(
                    min(vol_ratio / 2.0, 1.0),
                    text=f"Tỷ lệ: {vol_ratio:.2f}x trung bình"
                )
            else:
                st.caption("Chưa có dữ liệu volume phiên")

    sb_header("🏥 Sức khoẻ thị trường (400 mã HOSE)")
    render_breadth_panel(breadth)

    sb_header("💡 Khuyến nghị hành động")

    if reco is None:
        st.warning("⚠️ Chưa tính được khuyến nghị — thiếu dữ liệu kỹ thuật.")
    else:
        _cmap  = {"danger":"red","warning":"orange","success":"green","info":"blue","gray":"gray"}
        _emap  = {"danger":"🔴","warning":"🟠","success":"🟢","info":"🔵"}
        st_color     = _cmap.get(reco.get("color","gray"), "gray")
        action_emoji = _emap.get(reco.get("color","info"), "🔵")
        stock_pct    = reco.get("stock", 50) or 50
        cash_pct     = reco.get("cash",  50) or 50
        cur_score    = reco.get("score", 0)

        with st.container(border=True):
            ka, kb, kc, kd = st.columns([2.5, 1, 1, 1])
            with ka:
                st.markdown(f"## {action_emoji} :{st_color}[{reco['action']}]")
            kb.metric("🎯 Score",       f"{cur_score:+d}")
            kc.metric("📈 Tỷ trọng CP", f"{stock_pct}%")
            kd.metric("💵 Tiền mặt",    f"{cash_pct}%")

            st.progress(
                stock_pct / 100,
                text=f"Cổ phiếu {stock_pct}%  ·  Tiền mặt {cash_pct}%"
            )

            with st.expander("📋 Lý do khuyến nghị", expanded=True):
                reasons = reco.get("reasons", [])
                if reasons:
                    for r in reasons:
                        st.markdown(f"- {r}")
                else:
                    st.caption("Chưa có lý do chi tiết.")

        st.caption("⚠️ Khuyến nghị dựa trên PTKT + định giá, không phải tư vấn đầu tư chính thức.")

        with st.expander("📋 Bảng quy đổi Score → Tỷ trọng", expanded=False):
            st.caption(
                "Tổng Score = Breadth (–8→+8) + PTKT (–5→+5) + P/E (–2→+2) = khung –15 đến +15"
            )
            st.divider()

            score_table = [
                (12,  85, "20%", "🔥 MUA CỰC MẠNH"),
                (9,   75, "25%", "🚀 MUA MẠNH"),
                (6,   65, "35%", "🟢 MUA TÍCH CỰC"),
                (3,   58, "42%", "🟢 MUA / GIỮ"),
                (1,   52, "48%", "🟢 GIỮ CAO"),
                (-1,  50, "50%", "➖ CÂN BẰNG"),
                (-3,  42, "58%", "🟠 GIẢM NHẸ"),
                (-6,  30, "70%", "⚠️ GIẢM TỶ TRỌNG"),
                (-9,  20, "80%", "🔴 PHÒNG THỦ"),
                (-12, 10, "90%", "🛡️ PHÒNG THỦ MẠNH"),
                (-99,  5, "95%", "💀 THOÁT KHỎI THỊ TRƯỜNG"),
            ]

            h = st.columns([1.2, 1, 1, 2.5, 1.2])
            for col, lbl in zip(h, ["Score", "CP%", "Tiền%", "Hành động", ""]):
                col.markdown(f"**{lbl}**")

            matched = None
            for i, (thr, cp, cash, act) in enumerate(score_table):
                if cur_score >= thr:
                    matched = i
                    break

            for i, (thr, cp, cash, act) in enumerate(score_table):
                score_str = f"≥ {thr}" if thr > -99 else "< -12"
                cols = st.columns([1.2, 1, 1, 2.5, 1.2])
                cols[0].markdown(f"**{score_str}**")
                cols[1].markdown(f"`{cp}%`")
                cols[2].markdown(f"`{cash}`")
                cols[3].markdown(act)
                if i == matched:
                    cols[4].markdown("⬅️ **Hiện tại**")

# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU
# ==========================================
@st.fragment
def render_screener_fragment():
    sb_header(f"🔍 Danh sách quét sàn {exchange_choice}")
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
        st.markdown(
            '<div class="sb-note">Hãy cấu hình thông số ở Sidebar trái và bấm '
            '<b>🚀 KÍCH HOẠT QUÉT TOÀN DIỆN</b> để bắt đầu. '
            'Kết quả sau khi quét xong sẽ hiển thị ở tab <b>📊 Kết Quả Quét</b>.</div>',
            unsafe_allow_html=True,
        )
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
    sb_header("📊 Kết quả quét")
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
    sb_header("📡 Tín hiệu & cảnh báo")
    df_display_cached = st.session_state.get('df_display_cached')
    if isinstance(df_display_cached, pd.DataFrame) and not df_display_cached.empty:
        render_screener_signals(df_display_cached, signal_filter)
    else:
        st.info("Chưa có dữ liệu quét. Sang tab **🔍 Bộ Lọc** để quét, rồi ghé tab **📊 Kết Quả Quét** trước.")

# ==========================================
# TAB 5: KHUYẾN NGHỊ
# ==========================================

with tab_recommendation:
    render_recommendation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift) 

# ========================================== 
# TAB 6: SCREENER SỨC BẬT 
# ========================================== 
with tab_suc_bat: 
    render_suc_bat_tab()

# ==========================================
# TAB 7: QUẢN LÝ GIAO DỊCH (PORTFOLIO MANAGER)
# ==========================================
with tab_portfolio:
    render_portfolio_v2_tab(PRIORITY_TICKERS)
