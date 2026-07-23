import streamlit as st
import pandas as pd
import concurrent.futures
import time
import streamlit.components.v1 as components
from supabase import create_client
import traceback

from indicators import market_snapshot
from trend_engine import market_recommendation
from tab_accumulation import render_accumulation_tab
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex, set_rate_limit
from indicators import safe_market_snapshot as market_snapshot, _empty_snapshot
from indicators import calculate_technical_signals
import trend_engine as te
from ui_layout import render_sidebar, render_market_tab, render_screener_results, render_screener_signals
from ux_components import setup_cache_clear_button, render_search_and_export
import backtester as bt

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

# --- 2. KẾT NỐI SUPABASE (an toàn: thiếu secrets vẫn không làm sập app) ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_connection()

# --- Danh sách mã bị đình chỉ / hạn chế giao dịch (tự bổ sung khi phát hiện) ---
BLACKLIST = {"BCG", "HBC", "HNG", "POM", "HAG", "ITA", "TGG", "TTB"}

# --- Danh sách mã vốn hoá lớn / thanh khoản cao (VN30 + một số mã lớn khác) ---
# Dùng để: (1) ưu tiên quét trước -> có kết quả hợp lệ xuất hiện nhanh trong vài giây,
# (2) làm "Chế độ NHANH" -> chỉ quét nhóm này, gần như chắc chắn đủ thanh khoản >=20 tỷ/phiên
# nên tỷ lệ hợp lệ cao, tránh lãng phí quota vào các mã nhỏ chắc chắn bị lọc bỏ.
PRIORITY_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "DGC", "DPM", "DCM", "PVD", "PVS", "GEX", "KDH", "NLG", "DXG", "PDR",
    "VND", "HCM", "VCI", "BSI", "CTS", "MSB", "OCB", "EIB", "LPB", "SGB",
    "REE", "GMD", "HAH", "PNJ", "DGW", "FRT", "VTP", "ANV", "VHC", "DBC",
]

# --- 3. KHỞI TẠO BIẾN CHO GIAO DIỆN ---
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, vnstock_api_key, fast_mode = render_sidebar()

# --- Đăng ký API Key vnstock (nếu có) để tăng giới hạn tốc độ từ 20 -> 60 request/phút ---
# Không có key: tài khoản "khách" chỉ được 20 request/phút -> quét 1500 mã sẽ mất hơn 1 tiếng
# và trông giống như bị "kẹt" dù thực chất vẫn đang chạy, chỉ là rất chậm.
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
        set_rate_limit(55)  # có API key -> hạn mức 60/phút, để dư an toàn 55
    except Exception:
        set_rate_limit(18)
else:
    set_rate_limit(18)  # tài khoản khách -> hạn mức 20/phút, để dư an toàn 18

setup_cache_clear_button()

st.title("📈 Dashboard Phân Tích Dòng Tiền & Kỹ Thuật")
# --- 4. TẠO 5 TAB ---
tab_market, tab_screener, tab_results, tab_signals, tab_simulation, tab_backtest, tab_reports, tab_accum = st.tabs([
    "🌟 Thị Trường", "🔍 Bộ Lọc", "📊 Kết Quả Quét", "📡 Tín Hiệu & Cảnh Báo", "🔮 Mô Phỏng", "🛠️ Backtest", "📑 Báo Cáo", "🧭 Tích Lũy"
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
# 🆕 PHÂN TÍCH XU HƯỚNG & KHUYẾN NGHỊ THỊ TRƯỜNG
# ============================================================
st.markdown("---")
st.markdown("### 🧠 Phân tích Xu hướng & Khuyến nghị Thị trường")

snap = market_snapshot(symbol="VNINDEX", days=250)
reco = market_recommendation(snap)

# --- Hàng 1: Xu hướng giá | Dòng tiền ---
c1, c2 = st.columns(2)

with c1:
    with st.container(border=True):
        st.markdown("#### 📈 Xu hướng giá")
        st.markdown(f"### {snap['trend_text']}")
        st.caption(snap["ma20_text"])

        m1, m2, m3 = st.columns(3)
        m1.metric("MA20",  f"{snap['ma20']:.1f}"  if snap['ma20']  else "—")
        m2.metric("MA50",  f"{snap['ma50']:.1f}"  if snap['ma50']  else "—")
        m3.metric("MA200", f"{snap['ma200']:.1f}" if snap['ma200'] else "—")

        st.markdown(
            f"**Hỗ trợ gần:** `{snap['support']:.1f}` &nbsp;•&nbsp; "
            f"**Kháng cự:** `{snap['resistance']:.1f}`"
        )

with c2:
    with st.container(border=True):
        st.markdown("#### 🔊 Dòng tiền (Volume)")
        st.markdown(f"### {snap['vol_text']}")

        v1, v2 = st.columns(2)
        v1.metric("Vol hôm nay", f"{snap['vol_today']:,.0f}")
        v2.metric("TB 20 phiên", f"{snap['vol_avg']:,.0f}")

        st.progress(
            min(snap["vol_ratio"] / 2.0, 1.0),
            text=f"Tỷ lệ: {snap['vol_ratio']}x trung bình"
        )

# --- Hàng 2: Chỉ báo KT | Khuyến nghị ---
c3, c4 = st.columns(2)

with c3:
    with st.container(border=True):
        st.markdown("#### 📊 Chỉ báo kỹ thuật")
        st.markdown(f"**RSI(14):** `{snap['rsi']}` — {snap['rsi_text']}")
        st.markdown(f"**MACD:** `{snap['macd']}` &nbsp;|&nbsp; "
                    f"**Signal:** `{snap['macd_signal']}`")
        st.markdown(f"**Trạng thái MACD:** :{snap['macd_color']}[{snap['macd_cross']}]")

with c4:
    with st.container(border=True):
        st.markdown("#### 💡 Khuyến nghị hành động")
        st.markdown(f"### :{reco['color']}[{reco['action']}]")

        s1, s2 = st.columns(2)
        s1.metric("📈 Nên nắm giữ CP", f"{reco['stock']}%")
        s2.metric("💵 Nên giữ tiền mặt", f"{reco['cash']}%")

        st.progress(reco["stock"] / 100,
                    text=f"Tỷ trọng CP {reco['stock']}% / Tiền {reco['cash']}%")

        with st.expander("📋 Lý do khuyến nghị", expanded=True):
            for r in reco["reasons"]:
                st.markdown(f"- {r}")

        st.caption("⚠️ Khuyến nghị dựa trên phân tích kỹ thuật, không phải tư vấn đầu tư chính thức.")    
# ==========================================
# TAB 2: BỘ LỌC CỔ PHIẾU (BẢN TRUY VẾT LỖI X-QUANG)
# ==========================================
# --- FIX "tab chồng tab": bọc toàn bộ tab Bộ Lọc vào 1 fragment riêng. ---
# Lý do lỗi cũ: khi bấm nút quét, Streamlit chạy LẠI TOÀN BỘ file từ trên xuống.
# Vòng quét bên dưới chạy đồng bộ, có thể mất tới 20 phút (hard_timeout), nên
# script bị "kẹt" ngay tại đây và CHƯA kịp chạy tới code của các tab phía sau
# (Kết Quả Quét, Tín Hiệu, Mô Phỏng, Backtest, Báo Cáo, Tích Lũy) trong lượt
# chạy đó -> các tab đó hiển thị trống/không có thông tin.
# @st.fragment cô lập phần quét: bấm nút chỉ rerun RIÊNG fragment này, các tab
# khác giữ nguyên nội dung đã render, không bị "trắng" trong lúc đang quét.
@st.fragment
def render_screener_fragment():
    st.subheader(f"Danh Sách Quét Sàn {exchange_choice}")
    scan_button = st.button("🚀 KÍCH HOẠT QUÉT TOÀN DIỆN", use_container_width=True, type="primary")

    if scan_button:
        ex_code = 'all' if exchange_choice == "Tất cả 3 sàn" else exchange_choice
        
        # 1. KIỂM TRA SỐ LƯỢNG MÃ THỰC TẾ
        tickers = get_all_tickers(ex_code)
        
        if tickers is None or len(tickers) == 0:
            st.error("⚠️ Lỗi từ data_loader.py: Hàm `get_all_tickers` trả về danh sách rỗng!")
        else:
            # Số mã "chuẩn thực tế" để đối chiếu PHẢI phụ thuộc sàn đang chọn — trước đây hardcode
            # cứng "~1525 mã" (tổng CẢ 3 sàn) dù đang chỉ quét riêng HOSE/HNX/UPCOM, gây hiểu lầm
            # là bị thiếu dữ liệu trong khi thực ra số lượng lấy về là đúng cho sàn đó.
            ref_range = {
                "HOSE": "~400-430 mã", "HNX": "~300 mã", "UPCOM": "~900 mã", "Tất cả 3 sàn": "~1500-1600 mã",
            }.get(exchange_choice, "")
            st.info(f"📊 Hệ thống đã lấy thành công danh sách **{len(tickers)}** mã từ API "
                    f"(sàn **{exchange_choice}**, chuẩn thực tế khoảng {ref_range}).")

            # ƯU TIÊN QUÉT NHÓM VỐN HOÁ LỚN / THANH KHOẢN CAO TRƯỚC:
            # -> có mã hợp lệ hiện ra ngay trong vài giây đầu thay vì phải chờ quét lần lượt
            #    hết các mã nhỏ (đa phần sẽ bị loại vì không đủ thanh khoản >=20 tỷ/phiên).
            ticker_set = set(tickers)
            priority_present = [t for t in PRIORITY_TICKERS if t in ticker_set]
            rest = [t for t in tickers if t not in set(priority_present)]

            if fast_mode:
                # Chế độ NHANH: chỉ quét nhóm ưu tiên (thường đủ thanh khoản) -> nhanh, ít lãng phí quota
                tickers_ordered = priority_present if priority_present else tickers
                st.caption(f"⚡ Chế độ NHANH đang bật: chỉ quét {len(tickers_ordered)} mã vốn hoá lớn/thanh khoản cao (tắt ở sidebar để quét toàn sàn).")
            else:
                tickers_ordered = priority_present + rest
                extra_scanned = max(0, max_scan - len(priority_present))
                if extra_scanned < len(rest) * 0.3:
                    # Cảnh báo đúng tình huống gây nhầm lẫn: tắt Chế độ NHANH nhưng "Số lượng mã quét
                    # tối đa" vẫn thấp -> chỉ thêm được vài chục mã "còn lại" (thường thanh khoản thấp,
                    # đa số sẽ bị loại), khiến tổng mã hợp lệ gần như không đổi so với lúc bật NHANH.
                    st.warning(
                        f"⚠️ Chế độ NHANH đã tắt, nhưng \"Số lượng mã quét tối đa\" đang chỉ để **{max_scan}** "
                        f"-> chỉ quét thêm được **{extra_scanned} mã** ngoài {len(priority_present)} mã ưu tiên "
                        f"(trong tổng {len(rest)} mã còn lại). Đa số mã thêm vào này là mã nhỏ/thanh khoản thấp "
                        "nên có thể vẫn bị loại gần hết, làm số mã hợp lệ trông không đổi. "
                        "**Hãy kéo thanh trượt \"Số lượng mã quét tối đa\" ở sidebar lên vài trăm — 1500+** "
                        "rồi bấm quét lại để thấy khác biệt rõ rệt (lưu ý: quét càng nhiều càng lâu)."
                    )

            tickers_to_scan = tickers_ordered[:max_scan]

            # ƯỚC TÍNH THỜI GIAN: vnstock giới hạn 20 request/phút (khách) hoặc 60/phút (có API key)
            rate_per_min = 60 if active_api_key else 20
            eta_min = len(tickers_to_scan) / rate_per_min
            st.caption(
                f"⏱️ Ước tính thời gian quét: khoảng **{eta_min:.1f} phút** "
                f"(giới hạn {rate_per_min} request/phút{' - đã dùng API key' if active_api_key else ' - tài khoản khách, chưa có API key'})."
            )

            scan_start_time = time.time()
            # Giới hạn thời gian CỨNG cho cả lượt quét: tối đa gấp 3 lần ETA, tối thiểu 4 phút,
            # tối đa 20 phút -> quét không bao giờ treo vô thời hạn, luôn dừng và trả kết quả đang có.
            hard_timeout = max(240, min(1200, eta_min * 60 * 3))

            live_results_box = st.empty()  # Bảng kết quả LIVE: cập nhật ngay khi có mã hợp lệ, không cần chờ quét xong hết

            with st.status(f"Đang quét {len(tickers_to_scan)} mã... (ước tính ~{eta_min:.1f} phút)", expanded=True) as status:
                progress_bar = st.progress(0)
                results = []
                error_logs = [] # Rổ chứa nguyên nhân kẹt data
                total = len(tickers_to_scan)
                processed = 0
                timed_out = False

                def process_ticker(ticker):
                    if ticker in BLACKLIST:
                        return {"status": "skip"}
                    
                    try:
                        # Bước 1: Lấy data (300 ngày lịch ~200 phiên -> đủ đệm an toàn cho đường 129 phiên,
                        # trước đây dùng days_back=200 chỉ ra ~140 phiên, sát ngưỡng tối thiểu 139 -> dễ trượt)
                        df = get_stock_data(ticker, days_back=300)
                        if df is None or df.empty:
                            return {"status": "error", "msg": f"{ticker}: Hàm get_stock_data không lấy được data (trả về None/Empty)."}
                        
                        # Bước 2: Tính toán chỉ báo
                        try:
                            res = calculate_technical_signals(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
                            if res is None:
                                return {"status": "error", "msg": f"{ticker}: Hàm calculate_technical_signals trả về None."}
                            return {"status": "success", "data": res}
                        
                        except Exception as e:
                            # Bắt lỗi cú pháp hoặc tính toán trong file indicators.py
                            return {"status": "error", "msg": f"{ticker}: Lỗi bên indicators.py -> {str(e)}"}
                            
                    except Exception as e:
                        # Bắt lỗi kết nối bên file data_loader.py
                        return {"status": "error", "msg": f"{ticker}: Lỗi bên data_loader.py -> {str(e)}"}

                # Chạy đa luồng. LƯU Ý: vnstock giới hạn số kết nối đồng thời cho tài khoản khách (~4),
                # dùng nhiều luồng hơn không giúp nhanh hơn mà chỉ gây tranh chấp / bị chặn nhiều hơn.
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

                            # Cập nhật nhãn + BẢNG KẾT QUẢ LIVE theo thời gian thực, không chờ quét xong hết
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
                                # Bảng LIVE chỉ hiện ~8 cột gọn để dễ theo dõi tiến độ khi đang quét.
                                # Bảng đầy đủ/chia nhóm (Tổng Quan, 3 Đường Định Giá, Tín Hiệu & Cảnh Báo)
                                # sẽ hiện ở các tab riêng sau khi quét xong (xem render_screener_results
                                # và render_screener_signals trong ui_layout.py) — tránh nhồi 20+ cột vào
                                # 1 bảng lúc đang quét, gây rối mắt và tràn ngang màn hình.
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
                        # Không thể "kill" cứng các luồng đang chạy dở, nhưng KHÔNG chờ nữa -> trả kết quả đang có ngay
                        executor.shutdown(wait=False, cancel_futures=True)

                # 2. XỬ LÝ GIAO DIỆN KHI CÓ LỖI
                if timed_out:
                    status.update(
                        label=f"⏳ Đã dừng do quá thời gian chờ ({hard_timeout/60:.0f} phút) — hiển thị {len(results)} mã đã quét được ({processed}/{total}).",
                        state="complete", expanded=False
                    )
                elif len(results) > 0:
                    status.update(label=f"✅ Quét xong {len(results)} mã hợp lệ!", state="complete", expanded=False)
                else:
                    status.update(label=f"❌ Quét thất bại toàn bộ! Xin xem chi tiết lỗi bên dưới.", state="error", expanded=True)

            live_results_box.empty()  # Xóa bảng live, phần dưới sẽ hiện bảng kết quả đầy đủ (có tìm kiếm/tải CSV)

            if timed_out:
                st.warning(
                    f"⏳ Đã dừng quét sau {hard_timeout/60:.0f} phút do quá giới hạn thời gian an toàn "
                    f"(mới xử lý {processed}/{total} mã). Kết quả bên dưới là những mã ĐÃ quét xong. "
                    "Muốn quét hết, hãy giảm 'Số lượng mã quét tối đa' ở sidebar hoặc thêm API key vnstock để tăng tốc."
                )

            # --- IN RA BỆNH ÁN NẾU BỊ KẸT ---
            if len(error_logs) > 0 and len(results) == 0:
                st.error("🚨 APP BỊ KẸT VÌ CÁC LỖI DƯỚI ĐÂY (Vui lòng gửi lại lỗi này để tôi fix tiếp):")
                with st.expander("MỞ RỘNG ĐỂ XEM CHI TIẾT LỖI NGẦM", expanded=True):
                    # In ra 10 lỗi đầu tiên để biết nguyên nhân
                    for err in error_logs[:10]:
                        st.code(err)
                    if len(error_logs) > 10:
                        st.write(f"... và {len(error_logs) - 10} mã khác bị lỗi y hệt.")
            
            st.session_state['scan_results'] = results

            # Quét xong -> làm 1 lần rerun TOÀN APP (không phải chỉ fragment) để
            # tab "📊 Kết Quả Quét" và "📡 Tín Hiệu & Cảnh Báo" đọc được dữ liệu mới
            # ngay lập tức, không cần người dùng phải tự bấm gì thêm. Lần rerun này
            # rất nhanh vì scan_button sẽ về False -> không quét lại từ đầu.
            st.rerun()

    if not st.session_state.get('scan_results', []):
        st.caption("Hãy cấu hình thông số ở Sidebar trái và bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' để bắt đầu. "
                    "Kết quả sau khi quét xong sẽ hiển thị ở tab **📊 Kết Quả Quét**.")
    else:
        n_found = len(st.session_state['scan_results'])
        st.success(f"✅ Đã có {n_found} mã trong kết quả quét gần nhất. "
                    "👉 Chuyển sang tab **📊 Kết Quả Quét** ở trên để xem bảng chi tiết, tìm mã, hoặc tải CSV.")


with tab_screener:
    render_screener_fragment()

# ==========================================
# TAB 2b: KẾT QUẢ QUÉT (tách riêng khỏi tab Bộ Lọc cho đỡ rối)
# ==========================================
with tab_results:
    st.subheader("📊 Kết Quả Quét")
    # Dùng list rỗng [] làm mặc định để không văng lỗi KeyError
    if st.session_state.get('scan_results', []):
        raw_df = pd.DataFrame(st.session_state['scan_results'])
        df_display = render_search_and_export(raw_df)
        st.session_state['df_display_cached'] = df_display  # để tab Tín Hiệu & Cảnh Báo dùng lại, khỏi tìm/lọc 2 lần
        render_screener_results(df_display, signal_filter)
    else:
        st.info("Chưa có dữ liệu quét. Sang tab **🔍 Bộ Lọc** để bấm 'KÍCH HOẠT QUÉT TOÀN DIỆN' trước.")

# ==========================================
# TAB 2c: TÍN HIỆU & CẢNH BÁO (RSI/MFI, cảnh báo tạo đỉnh, bắt đáy — tách riêng cho gọn)
# ==========================================
with tab_signals:
    st.subheader("📡 Tín Hiệu & Cảnh Báo")
    df_display_cached = st.session_state.get('df_display_cached')
    if isinstance(df_display_cached, pd.DataFrame) and not df_display_cached.empty:
        render_screener_signals(df_display_cached, signal_filter)
    else:
        st.info("Chưa có dữ liệu quét. Sang tab **🔍 Bộ Lọc** để quét, rồi ghé tab **📊 Kết Quả Quét** trước.")
# ==========================================
# TAB 3: MÔ PHỎNG XU HƯỚNG "CÔ TIÊN" (Kijun17 / Knife65 / Knife129)
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
            # Cần đủ lịch sử cho đường 129 phiên + vùng đệm swing/chikou -> lấy 500 ngày lịch (~330-350 phiên)
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
                    snap = te.get_latest_snapshot(eng)

                    # ---------------- TÓM TẮT TRẠNG THÁI HIỆN TẠI ----------------
                    xh = snap['xu_huong']
                    xh_display = {"Tăng": "🟢 Tăng", "Giảm": "🔴 Giảm", "Sideway": "🟡 Sideway"}.get(xh, xh)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Xu Hướng Hiện Tại", xh_display)
                    c2.metric("Cách Knife2-129", f"{snap['pct_vs_129']}%" if snap['pct_vs_129'] is not None else "—")
                    c3.metric("Vol / TB20", f"{snap['v_ratio']}x" if snap['v_ratio'] is not None else "—")
                    c4.metric("Hợp Bích (65≈129)", "✅ Có" if snap['hop_bich'] else "—")

                    badges = []
                    if snap['khong_mua_duoi']:
                        badges.append("🟢 Còn trong vùng KHÔNG MUA ĐUỔI (giá mới vừa vượt mây)")
                    if snap['canh_bao_mua_duoi']:
                        badges.append("⚠️ CẢNH BÁO MUA ĐUỔI — giá đã đi xa mây, rủi ro mua bằng lòng tham")
                    if snap['cau_truc_khoe']:
                        badges.append("💪 Cấu trúc khoẻ: đỉnh sau cao hơn đỉnh trước, đáy sau cao hơn đáy trước")
                    if snap['canh_bao_tao_dinh']:
                        badges.append("⚠️ CẢNH BÁO TẠO ĐỈNH — giá gần đỉnh nhưng thanh khoản kiệt dần")
                    if snap['vung_phan_phoi']:
                        badges.append("🚨 VÙNG PHÂN PHỐI — volume đột biến tại đỉnh + giá vượt xa 129 (~30%+)")
                    if badges:
                        st.info("  \n".join(badges))

                    # ---------------- BIỂU ĐỒ ----------------
                    plot_df = eng.tail(180).copy()
                    if 'time' in plot_df.columns:
                        plot_df['Ngay'] = pd.to_datetime(plot_df['time']).dt.strftime('%Y-%m-%d')
                        plot_df.set_index('Ngay', inplace=True)

                    import plotly.graph_objects as go
                    from plotly.subplots import make_subplots

                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                        vertical_spacing=0.03, row_heights=[0.8, 0.2])

                    # Nền màu theo Xu Hướng (tô dải liên tục cho từng đoạn Tăng/Giảm)
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

                    # Giá + 3 đường + mây nội bộ (Knife65 <-> Knife129)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['close'],
                                             line=dict(color='#e5e0f7', width=2), name='Giá Đóng Cửa'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['knife65'],
                                             line=dict(color='rgba(0, 200, 83, 0.5)', width=1), name='Knife1 (65)'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['knife129'],
                                             line=dict(color='rgba(255, 23, 68, 0.5)', width=1.5),
                                             fill='tonexty', fillcolor='rgba(128, 128, 128, 0.15)', name='Knife2 (129) — Mây'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['kijun17'],
                                             line=dict(color='#2962FF', width=1.5), name='Kijun (17)'), row=1, col=1)

                    # Chân sóng có xác nhận volume
                    chan_song = plot_df[plot_df['xac_nhan_chan_song']]
                    fig.add_trace(go.Scatter(x=chan_song.index, y=chan_song['close'] * 0.97,
                                             mode='markers', marker=dict(symbol='triangle-up', size=14, color='lime'),
                                             name='🎯 Chân Sóng (Vol xác nhận)'), row=1, col=1)

                    # Hợp bích
                    hop_bich_pts = plot_df[plot_df['hop_bich']]
                    fig.add_trace(go.Scatter(x=hop_bich_pts.index, y=hop_bich_pts['knife129'],
                                             mode='markers', marker=dict(symbol='diamond', size=6, color='#FFD700'),
                                             name='💎 Hợp Bích (65≈129)'), row=1, col=1)

                    # Không mua đuổi (vùng mua đẹp) vs Cảnh báo mua đuổi
                    khong_duoi_pts = plot_df[plot_df['khong_mua_duoi']]
                    fig.add_trace(go.Scatter(x=khong_duoi_pts.index, y=khong_duoi_pts['close'],
                                             mode='markers', marker=dict(symbol='circle', size=5, color='#00E5FF'),
                                             name='✅ Vùng Không Mua Đuổi'), row=1, col=1)

                    # Cảnh báo tạo đỉnh / phân phối
                    dinh_pts = plot_df[plot_df['canh_bao_tao_dinh'] | plot_df['vung_phan_phoi']]
                    fig.add_trace(go.Scatter(x=dinh_pts.index, y=dinh_pts['close'] * 1.02,
                                             mode='markers', marker=dict(symbol='x', size=10, color='orange'),
                                             name='⚠️ Cảnh Báo Đỉnh/Phân Phối'), row=1, col=1)

                    # Điểm bắt đầu xu hướng Tăng/Giảm (chuyển trạng thái)
                    start_up = plot_df[plot_df['trend_start'] & (plot_df['Xu_Huong'] == 'Tăng')]
                    start_dn = plot_df[plot_df['trend_start'] & (plot_df['Xu_Huong'] == 'Giảm')]
                    fig.add_trace(go.Scatter(x=start_up.index, y=start_up['close'] * 0.95,
                                             mode='markers', marker=dict(symbol='star', size=13, color='#00C853'),
                                             name='🟢 Bắt Đầu Tăng'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=start_dn.index, y=start_dn['close'] * 1.05,
                                             mode='markers', marker=dict(symbol='star', size=13, color='#FF1744'),
                                             name='🔴 Bắt Đầu Giảm'), row=1, col=1)

                    # Volume
                    colors = ['#00C853' if row['close'] >= row['open'] else '#FF1744' for _, row in plot_df.iterrows()]
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['volume'], marker_color=colors, name='Volume'), row=2, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['vol_ma20'],
                                             line=dict(color='#FF6D00', width=2), name='Volume MA20'), row=2, col=1)

                    fig.update_layout(
                        title=f"<b>Mô Phỏng Xu Hướng Cô Tiên: {sim_ticker}</b>",
                        height=760, margin=dict(l=10, r=160, t=40, b=10),
                        showlegend=True,
                        # Legend NGANG (orientation="h") với 12 traces sẽ tràn khỏi khung nhìn và bị
                        # cắt/ẩn bớt mục -> đổi sang DỌC, đặt bên phải chart, không còn bị tràn.
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
                            "- **🎯 Chân Sóng**: phiên bắt đầu Tăng có khối lượng xác nhận (≥1.75x MA20, hoặc "
                            "≥2.5x nếu là đáy sau khi giá đã sụt ≥20% — đáy khủng hoảng).\n"
                            "- **💎 Hợp Bích**: Knife1(65) và Knife2(129) hội tụ sát nhau (≤0.14%) — dấu hiệu tích luỹ trước bùng nổ.\n"
                            "- **✅ Vùng Không Mua Đuổi**: đang Tăng và giá chỉ vừa vượt mây (≤3%) — vùng vào lệnh hợp lý.\n"
                            "- **⚠️ Cảnh Báo Đỉnh/Phân Phối**: giá gần đỉnh 20 phiên nhưng thanh khoản kiệt, "
                            "hoặc volume đột biến ngay đỉnh khi giá đã vượt xa Knife2-129 (~30%+)."
                        )
            else:
                st.warning(f"⚠️ Không có dữ liệu cho mã {sim_ticker}. Hãy kiểm tra lại mã cổ phiếu!")

# ==========================================
# TAB 4: HỆ THỐNG BACKTEST
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
# PATCH V4 - TAB 5: BÁO CÁO  TỪ CTCK
# Không dùng Supabase. Cào trực tiếp từ:
#   1. DNSE  — public API, không cần login
#   2. Vietstock Finance — endpoint public báo cáo 
#   3. CafeF — fallback HTML scrape
# Cache 4 giờ bằng st.cache_data để không cào lại mỗi lần bấm tab.
# ==========================================

import requests as _req
import pandas as _pd
from datetime import datetime as _dt, timedelta as _td
import streamlit as st

# ── NGUỒN 1: DNSE analyst recommendations (public, không cần auth) ──────────
@st.cache_data(ttl=14400, show_spinner=False)
def _fetch_dnse_reports(ticker: str = "") -> _pd.DataFrame:
    """
    DNSE public endpoint trả về khuyến nghị từ nhiều CTCK.
    Docs: https://developers.dnse.com.vn  (không cần key cho endpoint này)
    """
    rows = []
    try:
        # Endpoint tổng hợp khuyến nghị — DNSE trả JSON chuẩn UTF-8
        url = "https://finfo-api.dnse.com.vn/v3/analyst-recommendations"
        params = {"size": 200, "page": 1}
        if ticker:
            params["symbol"] = ticker.upper()

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
        }
        resp = _req.get(url, params=params, headers=headers, timeout=10)
        resp.encoding = "utf-8"

        if resp.status_code == 200:
            data = resp.json()
            # DNSE trả về list hoặc {"data": [...]}
            items = data if isinstance(data, list) else data.get("data", [])
            for item in items:
                rows.append({
                    "Ngày":           item.get("publishDate", item.get("date", ""))[:10],
                    "Mã":             item.get("symbol", item.get("ticker", "")),
                    "CTCK":           item.get("firm", item.get("company", item.get("analyst", ""))),
                    "Khuyến Nghị":    item.get("recommendation", item.get("action", "")),
                    "Giá Hiện Tại":   item.get("currentPrice", item.get("closePrice", 0)),
                    "Giá Mục Tiêu":   item.get("targetPrice", item.get("target_price", 0)),
                    "Nguồn":          "DNSE",
                    "Link PDF":       item.get("reportUrl", item.get("url", "")),
                })
    except Exception:
        pass
    return _pd.DataFrame(rows)


# ── NGUỒN 2: Vietstock báo cáo  (public JSON, không cần login) ─────
@st.cache_data(ttl=14400, show_spinner=False)
def _fetch_vietstock_reports(ticker: str = "") -> _pd.DataFrame:
    """
    Vietstock Finance public API — endpoint báo cáo  tổng hợp.
    Lấy 30 ngày gần nhất, filter theo ticker nếu có.
    """
    rows = []
    try:
        today   = _dt.now().strftime("%Y-%m-%d")
        from_dt = (_dt.now() - _td(days=30)).strftime("%Y-%m-%d")

        url = "https://finance.vietstock.vn/data/analyst-report"
        params = {
            "fromDate": from_dt,
            "toDate":   today,
            "page":     1,
            "pageSize": 200,
            "catID":    0,          # 0 = tất cả ngành
            "stockCode": ticker.upper() if ticker else "",
        }
        headers = {
            "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer":      "https://finance.vietstock.vn/bao-cao-phan-tich.htm",
            "Accept":       "application/json, text/javascript, */*",
            "Accept-Charset": "utf-8",
        }
        resp = _req.get(url, params=params, headers=headers, timeout=12)
        resp.encoding = "utf-8"

        if resp.status_code == 200:
            try:
                payload = resp.json()
            except Exception:
                return _pd.DataFrame(rows)

            # Vietstock thường trả {"data": [...]} hoặc list thẳng
            items = payload if isinstance(payload, list) else payload.get("data", payload.get("Data", []))
            for item in items:
                stock = item.get("StockCode", item.get("stockCode", item.get("Symbol", "")))
                rows.append({
                    "Ngày":         (item.get("PublishDate", item.get("publishDate", "")) or "")[:10],
                    "Mã":           stock,
                    "CTCK":         item.get("AnalystFirmName", item.get("Source", item.get("source", ""))),
                    "Khuyến Nghị":  item.get("Recommendation", item.get("recommendation", item.get("Action", ""))),
                    "Giá Hiện Tại": item.get("CurrentPrice", item.get("closePrice", 0)),
                    "Giá Mục Tiêu": item.get("TargetPrice",  item.get("targetPrice", 0)),
                    "Nguồn":        "Vietstock",
                    "Link PDF":     item.get("ReportUrl", item.get("reportUrl", item.get("DocumentUrl", ""))),
                })
    except Exception:
        pass
    return _pd.DataFrame(rows)


# ── NGUỒN 3: CafeF tổng hợp khuyến nghị (HTML scrape, fallback) ─────────────
@st.cache_data(ttl=14400, show_spinner=False)
def _fetch_cafef_reports(ticker: str = "") -> _pd.DataFrame:
    """
    CafeF trang khuyến nghị  — scrape bảng HTML.
    URL: https://cafef.vn/thi-truong-chung-khoan/khuyen-nghi-dau-tu.chn
    """
    rows = []
    try:
        from bs4 import BeautifulSoup

        url = "https://cafef.vn/thi-truong-chung-khoan/khuyen-nghi-dau-tu.chn"
        if ticker:
            url = f"https://cafef.vn/du-lieu/bao-cao/{ticker.lower()}-0.chn"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Charset": "utf-8",
        }
        resp = _req.get(url, headers=headers, timeout=12)
        resp.encoding = "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"class": lambda c: c and "tbl" in c.lower()})
        if not table:
            return _pd.DataFrame(rows)

        headers_row = [th.get_text(strip=True) for th in table.find_all("th")]
        for tr in table.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) >= 4:
                link_tag = tr.find("a", href=True)
                link = "https://cafef.vn" + link_tag["href"] if link_tag else ""
                rows.append({
                    "Ngày":         tds[0] if len(tds) > 0 else "",
                    "Mã":           tds[1] if len(tds) > 1 else ticker,
                    "CTCK":         tds[2] if len(tds) > 2 else "",
                    "Khuyến Nghị":  tds[3] if len(tds) > 3 else "",
                    "Giá Hiện Tại": tds[4] if len(tds) > 4 else 0,
                    "Giá Mục Tiêu": tds[5] if len(tds) > 5 else 0,
                    "Nguồn":        "CafeF",
                    "Link PDF":     link,
                })
    except Exception:
        pass
    return _pd.DataFrame(rows)


# ── HÀM TỔNG HỢP: gọi song song 3 nguồn, gộp lại, dedup ───────────────────
@st.cache_data(ttl=14400, show_spinner=False)
def _fetch_all_reports(ticker: str = "") -> _pd.DataFrame:
    import concurrent.futures
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(_fetch_dnse_reports,      ticker): "DNSE",
            ex.submit(_fetch_vietstock_reports,  ticker): "Vietstock",
            ex.submit(_fetch_cafef_reports,      ticker): "CafeF",
        }
        for future in concurrent.futures.as_completed(futures, timeout=15):
            try:
                df = future.result()
                if df is not None and not df.empty:
                    results.append(df)
            except Exception:
                pass

    if not results:
        return _pd.DataFrame()

    df_all = _pd.concat(results, ignore_index=True)

    # Chuẩn hoá cột số
    for col in ["Giá Hiện Tại", "Giá Mục Tiêu"]:
        df_all[col] = _pd.to_numeric(
            df_all[col].astype(str).str.replace(",", "").str.replace(".", ""),
            errors="coerce"
        ).fillna(0)

    # Tính Kỳ Vọng Upside %
    mask = (df_all["Giá Hiện Tại"] > 0) & (df_all["Giá Mục Tiêu"] > 0)
    df_all["Upside (%)"] = 0.0
    df_all.loc[mask, "Upside (%)"] = (
        (df_all.loc[mask, "Giá Mục Tiêu"] - df_all.loc[mask, "Giá Hiện Tại"])
        / df_all.loc[mask, "Giá Hiện Tại"] * 100
    ).round(1)

    # Sắp xếp mới nhất trước
    df_all = df_all.sort_values("Ngày", ascending=False).reset_index(drop=True)

    # Dedup: cùng Ngày + Mã + CTCK thì giữ 1
    df_all = df_all.drop_duplicates(subset=["Ngày", "Mã", "CTCK"], keep="first")

    return df_all


# PATCH V5 - TAB 5: BÁO CÁO 
# Đọc reports.json từ GitHub raw URL — không bị chặn bởi Streamlit Cloud.
# Bot GitHub Actions cào dữ liệu 2 lần/ngày và commit file này lên repo.
# ================================================================
# CÁCH ĐẶT GITHUB_RAW_BASE vào Streamlit Secrets:
#   GITHUB_RAW_BASE = "https://raw.githubusercontent.com/nnnhutien-cpu/Fairy-stock/main"
# ================================================================

with tab_reports:
    st.subheader("📑 Hệ Thống  Định Giá Cổ Phiếu")
    st.caption(
        "Dữ liệu tổng hợp tự động từ **DNSE · Vietstock · CafeF** — "
        "bot cập nhật 2 lần/ngày (10:00 SA & 15:30 CH)."
    )

    # ── Bộ lọc ──────────────────────────────────────────────────────────────
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

    # ── Load reports.json từ GitHub raw ─────────────────────────────────────
    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_reports_json() -> dict:
        import requests as _r
        # Ưu tiên lấy base URL từ secrets, fallback về hardcode repo này
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

    if force_refresh:
        _load_reports_json.clear()

    with st.spinner("Đang tải dữ liệu báo cáo..."):
        payload = _load_reports_json()

    # ── Xử lý lỗi load ──────────────────────────────────────────────────────
    if "error" in payload and not payload.get("data"):
        st.error(
            f"⚠️ Không tải được reports.json: `{payload['error']}`\n\n"
            "**Kiểm tra:**\n"
            "1. File `reports.json` đã có trong repo chưa? "
            "Vào GitHub → Actions → chạy thủ công workflow **Scrape Analyst Reports**.\n"
            "2. Repo có public không? Nếu private cần thêm token vào secrets.\n"
        )
        st.stop()

    # ── Dựng DataFrame ───────────────────────────────────────────────────────
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

    # Chuẩn hoá kiểu dữ liệu
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

    # ── Áp filter ────────────────────────────────────────────────────────────
    df_show = df_all.copy()
    if rep_ticker:
        df_show = df_show[df_show["ticker"].str.upper() == rep_ticker]
    if filter_action != "Tất cả":
        df_show = df_show[
            df_show["action"].str.upper().str.contains(filter_action, na=False)
        ]
    if filter_source != "Tất cả":
        df_show = df_show[df_show["source"] == filter_source]

    # ── Metrics ──────────────────────────────────────────────────────────────
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
                "date":        st.column_config.TextColumn("📅 Ngày"),
                "ticker":      st.column_config.TextColumn("🏷️ Mã"),
                "company":     st.column_config.TextColumn("🏢 CTCK"),
                "action":      st.column_config.TextColumn("⚡ Khuyến Nghị"),
                "buy_price":   st.column_config.NumberColumn("💰 Giá Khuyến Nghị", format="%d ₫"),
                "target_price":st.column_config.NumberColumn("🎯 Giá Mục Tiêu",    format="%d ₫"),
                "upside_pct":  st.column_config.NumberColumn("🚀 Upside",          format="%.1f %%"),
                "source":      st.column_config.TextColumn("🔗 Nguồn"),
                "report_url":  st.column_config.LinkColumn("📥 Báo Cáo", display_text="Xem"),
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
# TAB 8: CHIẾN LƯỢC TÍCH LŨY (RSI + MÂY + MA129 + DÒNG TIỀN)
# ==========================================
with tab_accum:
    render_accumulation_tab(get_stock_data, p_tenkan, p_kijun, p_senkou_b, p_shift)
