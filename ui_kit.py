"""
ui_kit.py — Bộ giao diện dùng chung cho MỌI tab của Cô Tiên Stock.

  inject_css()            : CSS toàn app (1 nguồn duy nhất, trước đây nằm rải trong main.py + từng tab)
  page_header(title, sub) : khung tiêu đề đầu mỗi tab
  section(title)          : tiêu đề mục nhỏ
  note(html)              : ô ghi chú viền trái
  style_fig(fig, height)  : khoác cùng 1 "theme" cho mọi biểu đồ plotly
Bảng màu biểu đồ đã kiểm tra độ tương phản & mù màu trên nền tối #0f0a1f.
"""
import streamlit as st

# ── Màu dùng chung ──
INK = "#e8e4ff"          # chữ chính / đường giá
MUTED = "#8b84a8"        # chữ phụ, trục
GRID = "rgba(139,132,168,0.14)"
UP, DOWN, WARN = "#22c55e", "#ef4444", "#f5a524"   # tăng / giảm / cảnh báo (kèm chữ, không dùng màu đơn lẻ)
VOL = "#4b4370"          # cột khối lượng trung tính
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"]  # thứ tự cố định, không xoay vòng

_CSS = """
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
    .val-up   { color: #22c55e !important; }
    .val-down { color: #ef4444 !important; }
    .val-warn { color: #f5a524 !important; }
    .lk-section { font-size: 11px; color: #8b7fb5; text-transform: uppercase;
                   letter-spacing: .6px; margin: 14px 0 8px;
                   border-bottom: 1px solid #2c2151; padding-bottom: 4px; }
    .sr-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .sr-table th { color: #666; font-weight: 400; text-align: left;
                   padding: 4px 8px; font-size: 11px; text-transform: uppercase; }
    .sr-table td { padding: 5px 8px; border-bottom: 1px solid #1e1a33; color: #ccc; }
    .sr-table tr:last-child td { border-bottom: none; }
    .badge-r { background:#3a1a1f; color:#ef4444; padding:2px 8px;
               border-radius:4px; font-size:11px; font-weight:600; }
    .badge-s { background:#12301f; color:#22c55e; padding:2px 8px;
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

    /* ══════════ Đồng bộ font cho NỘI DUNG mọi tab ══════════ */
    h4, h5, h6 { color: #a394d4 !important; font-weight: 700 !important; letter-spacing: .2px; }

    /* SỬA: bỏ ".stMarkdown div" vì nó ghi đè font-size/màu của .sb-title, .lk-value, .sb-stat-value... */
    .stMarkdown p, .stMarkdown li,
    [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {
        font-size: 13px !important; color: #ccc !important; line-height: 1.6 !important;
    }

    [data-testid="stCaptionContainer"], .stCaption, small {
        font-size: 12px !important; color: #888 !important;
    }

    [data-testid="stDataFrame"], [data-testid="stDataFrame"] * ,
    [data-testid="stTable"], [data-testid="stTable"] * {
        font-family: 'Sora', sans-serif !important;
        font-size: 13px !important;
    }

    [data-testid="stExpander"] summary,
    .streamlit-expanderHeader, details > summary {
        font-size: 13px !important; font-weight: 700 !important; color: #a394d4 !important;
    }
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] p {
        font-size: 13px !important;
    }

    .stRadio label, .stCheckbox label, .stSelectbox label,
    .stTextInput label, .stSlider label, .stNumberInput label,
    [data-testid="stWidgetLabel"] p {
        font-size: 12px !important; color: #a99fcf !important; font-weight: 600 !important;
    }
    .stRadio [data-testid="stMarkdownContainer"] p,
    .stCheckbox [data-testid="stMarkdownContainer"] p {
        font-size: 13px !important; color: #dcd6ec !important;
    }

    [data-testid="stAlert"] p, [data-testid="stAlert"] div {
        font-size: 13px !important;
    }

    .stTabs [data-baseweb="tab"] p { font-size: .9rem !important; font-weight: 600 !important; }

    /* ══════════ Thanh điều hướng (thay st.tabs: chỉ trang đang mở mới chạy -> app nhanh hơn) ══════════ */
    div[data-testid="stButtonGroup"] { gap: 6px !important; flex-wrap: wrap; }
    div[data-testid="stButtonGroup"] button {
        border-radius: 10px !important; border: 1px solid #2c2151 !important;
        background: #17112e !important; color: #a99fcf !important;
        font-weight: 600 !important; padding: 6px 14px !important;
    }
    div[data-testid="stButtonGroup"] button p { font-size: .88rem !important; color: inherit !important; }
    div[data-testid="stButtonGroup"] button[kind$="Active"],
    div[data-testid="stButtonGroup"] button[aria-checked="true"] {
        background: linear-gradient(90deg, #4c1d95, #6d28d9) !important; color: #ffffff !important; border-color: transparent !important;
    }
    .app-title { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
    .app-title .name { font-size: 1.55rem; font-weight: 800; color: #e8e4ff; letter-spacing: .3px; }
    .app-title .tag  { font-size: 12px; color: #8b84a8; }
    .lk-section { font-size: 11px !important; }
    div[data-testid="stMetric"] { padding: 12px 14px !important; box-shadow: none !important; }
    div[data-testid="stMetricValue"] { font-size: 1.35rem !important; font-variant-numeric: tabular-nums; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color: #2c2151 !important; }
    /* ── Mở rộng riêng cho tab Portfolio v2 ── */
    .badge-hold    { background:#3a2f14; color:#f5a524; padding:2px 8px;
                     border-radius:4px; font-size:11px; font-weight:600; }
    .badge-sell25  { background:#3a2414; color:#f97316; padding:2px 8px;
                     border-radius:4px; font-size:11px; font-weight:600; }
    .badge-sellall { background:#3a1a1f; color:#ef4444; padding:2px 8px;
                     border-radius:4px; font-size:11px; font-weight:600; }
    .badge-buy     { background:#12301f; color:#22c55e; padding:2px 8px;
                     border-radius:4px; font-size:11px; font-weight:600; }
    .badge-wait    { background:#1e1a33; color:#8b7fb5; padding:2px 8px;
                     border-radius:4px; font-size:11px; font-weight:600; }
    
    .slot-card {
        background: #1e1e2e; border: 1px solid #2c2151;
        border-radius: 14px; padding: 18px 10px 14px 10px;
        text-align: center; min-height: 108px;
    }
    .slot-card.empty {
        background: #16162a; border: 2px dashed #3a2f66;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
    }
    .slot-empty-plus { color: #5a4a8a; font-size: 1.8rem; line-height: 1; }
    .slot-empty-label { color: #5a4a8a; font-size: .75rem; margin-top: 4px; }
    .slot-ticker { font-weight: 800; font-size: 1.15rem; color: #e0e0ff; letter-spacing: .5px; }
    .slot-pct { font-size: .72rem; color: #888; margin-top: 2px; }
    .slot-action-wrap { margin-top: 10px; }
    
    .buy-confirm-card {
        background: #12102a; border: 1px solid #12301f;
        border-radius: 10px; padding: 12px 10px; text-align: center;
    }
    .buy-confirm-ticker { font-weight: 700; font-size: 1rem; color: #e0e0ff; }
    .buy-confirm-note { font-size: .75rem; color: #22c55e; margin-top: 4px; }
    
    @media (max-width: 760px) {
        .block-container { padding-left: 1rem !important; padding-right: 1rem !important; padding-top: 1.5rem !important; }
        .lk-grid { grid-template-columns: repeat(2, 1fr) !important; }
    }
</style>
"""


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def app_title(name="🧚‍♀️ Cô Tiên Stock", tag="Dashboard phân tích dòng tiền & kỹ thuật"):
    st.markdown(f'<div class="app-title"><span class="name">{name}</span><span class="tag">{tag}</span></div>',
                unsafe_allow_html=True)


def page_header(title, sub=""):
    sub_html = f'<div class="sb-sub">{sub}</div>' if sub else ""
    st.markdown(f'<div class="sb-header"><div class="sb-title">{title}</div>{sub_html}</div>',
                unsafe_allow_html=True)


def section(title):
    st.markdown(f'<div class="lk-section">{title}</div>', unsafe_allow_html=True)


def note(html):
    st.markdown(f'<div class="sb-note">{html}</div>', unsafe_allow_html=True)


def style_fig(fig, height=420, dates=True, legend=True):
    """Theme chung cho plotly: nền trong suốt, chữ Sora, lưới mờ, hover gộp theo trục x."""
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=30, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Sora, sans-serif", size=12, color=MUTED),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(color=INK)),
        hovermode="x unified", hoverlabel=dict(bgcolor="#1a1436", font_color=INK),
        xaxis_rangeslider_visible=False, dragmode="pan",
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, showline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False)
    if dates:
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    for ann in fig.layout.annotations or []:  # tiêu đề subplot
        ann.font = dict(color=INK, size=12)
    return fig


CHART_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def plot(fig):
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)
