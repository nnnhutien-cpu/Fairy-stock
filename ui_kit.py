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
/* ═══════════════════════════════════════════════════════════════════
   Cô Tiên Stock — giao diện chung.
   Màu nền, font Sora, ô nhập, bảng dữ liệu đã đặt trong .streamlit/config.toml
   (theme gốc) -> ở đây KHÔNG ép font lên mọi phần tử nữa (trước đây làm vỡ
   icon: hiện chữ "arrow_right", "visibility" chồng lên nhãn).
   ═══════════════════════════════════════════════════════════════════ */
:root{
  --bg:#0f0a1f; --panel:#17112e; --card:#1a1436; --card-2:#12102a;
  --line:#2c2151; --line-soft:#231a42;
  --ink:#e8e4ff; --text:#cfc8ea; --muted:#8b84a8; --dim:#6d6690;
  --accent:#8b5cf6; --accent-2:#a78bfa; --grad:linear-gradient(135deg,#5b21b6 0%,#7c3aed 55%,#8b5cf6 100%);
  --up:#22c55e; --down:#ef4444; --warn:#f5a524;
  --ease:cubic-bezier(.2,.7,.2,1);
}

/* ── Nền & khung ── */
.stApp{ background: radial-gradient(1200px 600px at 85% -10%, rgba(124,58,237,.16), transparent 60%), var(--bg); }
header[data-testid="stHeader"]{ background: transparent; }
[data-testid="stDecoration"]{ display:none; }
.block-container{ padding: 2.6rem 2.2rem 3rem !important; max-width: 1480px !important; }
section[data-testid="stSidebar"] .block-container{ padding: 1.6rem 1.1rem !important; }

/* ── Mượt: không làm mờ cả trang mỗi lần chạy lại, chỉ hiện vào nhẹ ── */
[data-stale="true"]{ opacity: 1 !important; transition: none !important; }
[data-testid="stMainBlockContainer"] > div{ animation: ct-fade .28s var(--ease) both; }
@keyframes ct-fade{ from{ opacity:0; transform: translateY(4px);} to{ opacity:1; transform:none;} }
@media (prefers-reduced-motion: reduce){ *{ animation:none !important; transition:none !important; } }

/* ── Chữ ── */
h1,h2,h3,h4,h5,h6{ color: var(--ink) !important; letter-spacing:-.01em; }
h5,h6{ color: var(--accent-2) !important; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li{ color: var(--text); line-height:1.6; }
[data-testid="stCaptionContainer"]{ color: var(--muted) !important; }
[data-testid="stWidgetLabel"] p{ color: #b3aad6 !important; font-weight:600 !important; font-size:.82rem !important; }
.stApp, [data-testid="stMetricValue"], [data-testid="stDataFrame"]{ font-variant-numeric: tabular-nums; }

/* ── Nút ── */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button{
  font-weight:600; border:1px solid var(--line); background: var(--card);
  transition: transform .15s var(--ease), box-shadow .2s var(--ease), border-color .2s, background .2s;
  white-space: normal; line-height:1.25; min-height: 2.6rem;
}
.stButton > button:hover, .stDownloadButton > button:hover{ border-color: var(--accent); transform: translateY(-1px); }
.stButton > button:active, .stDownloadButton > button:active{ transform: translateY(0); }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"]{
  background: var(--grad); border: none; color:#fff; box-shadow: 0 6px 18px -8px rgba(139,92,246,.7);
}
.stButton > button[kind="primary"]:hover{ box-shadow: 0 10px 24px -8px rgba(139,92,246,.85); }

/* ── Thanh điều hướng trang ── */
div[data-testid="stButtonGroup"]{ gap:6px !important; flex-wrap:wrap; margin: 2px 0 14px; }
div[data-testid="stButtonGroup"] button{
  border-radius: 999px !important; border:1px solid var(--line) !important;
  background: rgba(26,20,54,.7) !important; color:#b3aad6 !important;
  font-weight:600 !important; padding: 6px 15px !important;
  transition: background .2s var(--ease), color .2s, border-color .2s;
}
div[data-testid="stButtonGroup"] button:hover{ border-color: var(--accent) !important; color: var(--ink) !important; }
div[data-testid="stButtonGroup"] button[kind$="Active"],
div[data-testid="stButtonGroup"] button[aria-checked="true"]{
  background: var(--grad) !important; color:#fff !important; border-color: transparent !important;
  box-shadow: 0 6px 16px -8px rgba(139,92,246,.8);
}

/* ── Tab con ── */
.stTabs [data-baseweb="tab-list"]{ gap:4px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{ padding: 8px 14px; color: var(--muted); font-weight:600; transition: color .2s; }
.stTabs [data-baseweb="tab"]:hover{ color: var(--ink); }
.stTabs [aria-selected="true"]{ color: var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background: var(--accent) !important; height:2px; }
.stTabs [data-baseweb="tab-panel"]{ padding-top: 14px; }

/* ── Thẻ số liệu ── */
div[data-testid="stMetric"]{
  background: linear-gradient(180deg, var(--card), #161031);
  border:1px solid var(--line); border-radius:14px; padding: 14px 16px;
  transition: border-color .2s, transform .2s var(--ease);
}
div[data-testid="stMetric"]:hover{ border-color:#3d2e70; }
[data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] div{
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
  color: var(--muted) !important; font-size: .8rem !important; font-weight:600 !important;
}
[data-testid="stMetricValue"]{ color: var(--ink); font-weight:700; font-size: 1.4rem !important; }

/* ── Khung viền, expander, bảng, cảnh báo ── */
[data-testid="stVerticalBlockBorderWrapper"]{ border-radius:16px; }
div[data-testid="stExpander"] details{ border-radius:12px; border-color: var(--line); background: rgba(23,17,46,.55); }
div[data-testid="stExpander"] summary:hover{ color: var(--ink); }
[data-testid="stDataFrame"], [data-testid="stTable"]{ border-radius:12px; overflow:hidden; }
[data-testid="stAlert"]{ border-radius:12px; }
[data-testid="stProgress"] > div > div > div > div{ background: var(--grad); }

/* ── Sidebar ── */
section[data-testid="stSidebar"]{ border-right:1px solid var(--line); }
.side-brand{ display:flex; align-items:center; gap:10px; margin: 0 0 4px; }
.side-brand .logo{ width:38px; height:38px; border-radius:11px; display:grid; place-items:center;
  background: var(--grad); font-size:20px; box-shadow: 0 6px 16px -8px rgba(139,92,246,.9); }
.side-brand .t{ font-weight:800; font-size:1.05rem; color:var(--ink); letter-spacing:.02em; line-height:1.15; }
.side-brand .s{ font-size:.72rem; color:var(--muted); }
.side-sec{ font-size:.7rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--dim);
  margin: 18px 0 8px; }

/* ── Tiêu đề app & từng trang ── */
.app-title{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin: 0 0 10px; }
.app-title .name{ font-size:1.5rem; font-weight:800; color:var(--ink); letter-spacing:-.01em; }
.app-title .tag{ font-size:.8rem; color:var(--muted); }
.sb-header{
  position:relative; overflow:hidden;
  background: linear-gradient(135deg, rgba(91,33,182,.28), rgba(23,17,46,.9) 55%);
  border:1px solid var(--line); border-radius:16px; padding: 16px 20px; margin-bottom: 18px;
}
.sb-header::after{ content:""; position:absolute; right:-40px; top:-60px; width:180px; height:180px;
  border-radius:50%; background: radial-gradient(circle, rgba(167,139,250,.22), transparent 70%); }
.sb-title{ font-size:1.3rem; font-weight:800; color:var(--ink); position:relative; z-index:1; }
.sb-sub{ font-size:.8rem; color:var(--muted); margin-top:3px; position:relative; z-index:1; }
.sb-note{
  background: rgba(26,20,54,.7); border:1px solid var(--line-soft); border-left:3px solid var(--accent-2);
  padding: 11px 14px; border-radius: 0 10px 10px 0; font-size:.85rem; color: var(--text); margin-bottom:14px;
}

/* ── Thẻ tra cứu (Sức Bật, Khuyến nghị, Danh mục) ── */
.lk-card{ background: var(--card); border:1px solid var(--line); border-radius:16px; padding: 20px 22px; margin-bottom:16px; }
.lk-ticker{ font-size:1.75rem; font-weight:800; color: var(--accent-2); letter-spacing:.06em; }
.lk-company{ font-size:.85rem; color: var(--muted); margin: 2px 0 16px; }
.lk-grid{ display:grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px; }
.lk-metric{ background: var(--card-2); border:1px solid var(--line-soft); border-radius:12px; padding: 12px 14px; }
.lk-label{ font-size:.68rem; color: var(--muted); text-transform:uppercase; letter-spacing:.06em; font-weight:600; }
.lk-value{ font-size:1.35rem; font-weight:700; color: var(--ink); margin-top:4px; font-variant-numeric: tabular-nums; }
.lk-sub{ font-size:.7rem; color: var(--dim); margin-top:2px; }
.val-up{ color: var(--up) !important; } .val-down{ color: var(--down) !important; } .val-warn{ color: var(--warn) !important; }
.lk-section{ font-size:.72rem; font-weight:700; color: var(--accent-2); text-transform:uppercase; letter-spacing:.08em;
  margin: 16px 0 8px; padding-bottom:6px; border-bottom:1px solid var(--line); }
.sr-table{ width:100%; border-collapse:collapse; font-size:.85rem; }
.sr-table th{ color: var(--muted); font-weight:600; text-align:left; padding: 6px 8px; font-size:.7rem; text-transform:uppercase; letter-spacing:.05em; }
.sr-table td{ padding: 7px 8px; border-bottom:1px solid var(--line-soft); color: var(--text); font-variant-numeric: tabular-nums; }
.sr-table tr:last-child td{ border-bottom:none; }
.sr-table tr:hover td{ background: rgba(139,92,246,.06); }
.formula-note{ background: var(--card-2); border-left:3px solid var(--accent-2); padding: 10px 14px;
  border-radius: 0 10px 10px 0; font-size:.8rem; color: var(--muted); margin-top:12px; line-height:1.7; }
.warn-box{ background: rgba(245,165,36,.08); border:1px solid rgba(245,165,36,.3); border-radius:12px; padding:10px 14px; color:#f3d9a6; }

/* ── Dải chỉ số tóm tắt ── */
.sb-stat-row{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
.sb-stat{ background: var(--card); border:1px solid var(--line); border-radius:14px; padding: 12px 16px; flex:1; min-width:130px; }
.sb-stat-label{ font-size:.7rem; color: var(--muted); text-transform:uppercase; letter-spacing:.06em; font-weight:600; }
.sb-stat-value{ font-size:1.3rem; font-weight:800; color: var(--ink); margin-top:2px; font-variant-numeric: tabular-nums; }

/* ── Nhãn ── */
.badge-r,.badge-s,.badge-fib,.badge-hold,.badge-sell25,.badge-sellall,.badge-buy,.badge-wait,.src-badge{
  display:inline-block; padding: 2px 9px; border-radius:999px; font-size:.7rem; font-weight:700; letter-spacing:.02em; }
.badge-r,.badge-sellall{ background: rgba(239,68,68,.14); color:#f87171; }
.badge-s,.badge-buy{ background: rgba(34,197,94,.14); color:#4ade80; }
.badge-hold{ background: rgba(245,165,36,.14); color:#fbbf24; }
.badge-sell25{ background: rgba(249,115,22,.14); color:#fb923c; }
.badge-wait{ background: rgba(139,132,168,.16); color:#b3aad6; }
.badge-fib{ background: rgba(57,135,229,.14); color:#7cb0f5; }
.src-badge{ margin-left:6px; font-size:.62rem; }
.src-vci{ background: rgba(57,135,229,.14); color:#7cb0f5; }
.src-fireant{ background: rgba(34,197,94,.12); color:#4ade80; }
.src-yahoo{ background: rgba(139,92,246,.14); color: var(--accent-2); }

/* ── Danh mục: ô slot ── */
.slot-card{ background: var(--card); border:1px solid var(--line); border-radius:16px; padding: 18px 10px 14px;
  text-align:center; min-height:108px; transition: border-color .2s, transform .2s var(--ease); }
.slot-card:hover{ border-color:#3d2e70; transform: translateY(-1px); }
.slot-card.empty{ background: rgba(23,17,46,.5); border:2px dashed #3a2f66; display:flex; flex-direction:column;
  align-items:center; justify-content:center; }
.slot-empty-plus{ color:#6b5aa6; font-size:1.8rem; line-height:1; }
.slot-empty-label{ color:#6b5aa6; font-size:.75rem; margin-top:4px; }
.slot-ticker{ font-weight:800; font-size:1.15rem; color: var(--ink); letter-spacing:.04em; }
.slot-pct{ font-size:.72rem; color: var(--muted); margin-top:2px; }
.slot-action-wrap{ margin-top:10px; }
.buy-confirm-card{ background: var(--card-2); border:1px solid rgba(34,197,94,.3); border-radius:12px; padding: 12px 10px; text-align:center; }
.buy-confirm-ticker{ font-weight:700; font-size:1rem; color: var(--ink); }
.buy-confirm-note{ font-size:.75rem; color: var(--up); margin-top:4px; }

/* ── Điện thoại ── */
@media (max-width: 760px){
  .block-container{ padding: 1.6rem 1rem 2rem !important; }
  .lk-grid{ grid-template-columns: repeat(2,minmax(0,1fr)) !important; }
  .app-title .tag{ display:none; }
  .sb-title{ font-size:1.1rem; }
  div[data-testid="stButtonGroup"] button{ padding: 5px 11px !important; }
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
