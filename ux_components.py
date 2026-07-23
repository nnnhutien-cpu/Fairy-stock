"""
ux_enhancements.py
------------------
File UX bổ sung cho hệ thống Cô Tiên Stock:
  1. inject_smooth_ux()   -> CSS làm mượt giao diện (transition, hover, fade-in, scrollbar, loading bar)
  2. get_trend_color()    -> quy tắc màu chuẩn: TĂNG = xanh lá, GIẢM = đỏ, ĐỨNG GIÁ = tím nhạt (trung tính)
  3. render_trend_metric()-> metric tự đổi màu xanh/đỏ (đẹp hơn st.metric mặc định, đồng bộ theme tím)
  4. render_trend_badge() -> badge nhỏ dạng pill, dùng trong bảng / dòng chữ để nhấn mạnh tăng/giảm
  5. render_section_card()-> khung card bo góc, viền đổi màu theo xu hướng (dùng cho các khối phân tích)
  6. colorize_dataframe_column() -> tô màu 1 cột số trong DataFrame (âm đỏ, dương xanh) khi hiển thị

Cách dùng trong main.py:
    from ux_enhancements import inject_smooth_ux, render_trend_metric, render_section_card

    inject_smooth_ux()   # gọi 1 lần, ngay sau st.set_page_config(...)

    render_trend_metric("📊 Chỉ số VN-INDEX", current_index, index_change, suffix=" đ")

    render_section_card(
        title="🧠 Phân tích Xu hướng & Khuyến nghị Thị trường",
        change_value=index_change,
        body_up="Thị trường đang TĂNG. Ưu tiên tìm điểm mua theo nhịp điều chỉnh, hạn chế FOMO.",
        body_down="Thị trường đang GIẢM. Ưu tiên quản trị rủi ro, hạn chế bắt đáy sớm.",
        body_flat="Thị trường đi ngang. Quan sát thêm, chưa vội vào lệnh.",
    )
"""

import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# 1. BẢNG MÀU CHUẨN CHO TOÀN HỆ THỐNG
# ---------------------------------------------------------------------------
COLOR_UP = "#34d399"      # xanh lá – tăng
COLOR_DOWN = "#ff4d4f"    # đỏ – giảm
COLOR_FLAT = "#a99fcf"    # tím nhạt – đứng giá / trung tính
COLOR_BG_PURPLE = "#1a1436"


def get_trend_color(change_value, threshold: float = 0.0) -> str:
    """Trả về mã màu theo quy tắc: > threshold = xanh, < -threshold = đỏ, còn lại = trung tính."""
    if change_value is None:
        return COLOR_FLAT
    try:
        change_value = float(change_value)
    except (TypeError, ValueError):
        return COLOR_FLAT
    if change_value > threshold:
        return COLOR_UP
    if change_value < -threshold:
        return COLOR_DOWN
    return COLOR_FLAT


def _trend_icon(change_value) -> str:
    color = get_trend_color(change_value)
    if color == COLOR_UP:
        return "🟢▲"
    if color == COLOR_DOWN:
        return "🔴▼"
    return "⚪"


# ---------------------------------------------------------------------------
# 2. CSS LÀM MƯỢT GIAO DIỆN (gọi 1 LẦN duy nhất trong main.py)
# ---------------------------------------------------------------------------
def inject_smooth_ux():
    """Bơm CSS giúp giao diện mượt hơn: hiệu ứng fade-in, hover mềm, scrollbar tím, thanh loading mảnh."""
    st.markdown(
        f"""
        <style>
        /* Fade-in nhẹ khi mỗi block render lại (đỡ giật khi rerun) */
        div[data-testid="stVerticalBlock"] > div {{
            animation: fadeInUx 0.35s ease-in-out;
        }}
        @keyframes fadeInUx {{
            from {{ opacity: 0; transform: translateY(4px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}

        /* Hover mượt cho card metric */
        div[data-testid="stMetric"] {{
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }}
        div[data-testid="stMetric"]:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 22px rgba(109,40,217,.35);
            border-color: #6d28d9;
        }}

        /* Nút bấm mượt hơn */
        .stButton > button {{
            transition: transform .15s ease, filter .15s ease, box-shadow .15s ease;
        }}
        .stButton > button:active {{ transform: scale(0.97); }}

        /* Tab chuyển mượt */
        .stTabs [data-baseweb="tab"] {{
            transition: background .2s ease, color .2s ease;
        }}

        /* Progress bar mảnh, màu tím-hồng gradient thay vì đỏ mặc định */
        div[role="progressbar"] > div {{
            background: linear-gradient(90deg, #6d28d9, #34d399) !important;
        }}

        /* Scrollbar tím đồng bộ theme, mảnh và bo tròn */
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: {COLOR_BG_PURPLE}; }}
        ::-webkit-scrollbar-thumb {{
            background: #4a3a7a; border-radius: 8px;
        }}
        ::-webkit-scrollbar-thumb:hover {{ background: #6d28d9; }}

        /* DataFrame mượt hơn khi hover từng dòng */
        .stDataFrame [role="row"]:hover {{
            background: rgba(109,40,217,.12) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 3. METRIC TỰ ĐỔI MÀU XANH/ĐỎ (thay thế / bổ sung cho st.metric)
# ---------------------------------------------------------------------------
def render_trend_metric(label: str, value, change_value=None, suffix: str = "", value_fmt: str = "{:,.2f}"):
    """
    Vẽ 1 ô metric bo góc, viền + số liệu đổi màu theo xu hướng tăng/giảm.
    Dùng thay cho st.metric khi muốn kiểm soát màu chính xác (không phụ thuộc theme mặc định của Streamlit).
    """
    color = get_trend_color(change_value)
    icon = _trend_icon(change_value)
    try:
        value_str = value_fmt.format(value) + suffix
    except (TypeError, ValueError):
        value_str = f"{value}{suffix}"

    delta_html = ""
    if change_value is not None:
        try:
            change_str = f"{float(change_value):,.2f}{suffix}"
            sign = "+" if float(change_value) > 0 else ""
            delta_html = f'<div style="font-size:.85rem; font-weight:600; color:{color};">{icon} {sign}{change_str}</div>'
        except (TypeError, ValueError):
            pass

    st.markdown(
        f"""
        <div style="background:{COLOR_BG_PURPLE}; border:1px solid {color}55; border-radius:14px;
                    padding:14px 16px; transition: all .2s ease;">
            <div style="color:#a99fcf; font-size:.85rem;">{label}</div>
            <div style="color:#f2eeff; font-weight:700; font-size:1.5rem;">{value_str}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 4. BADGE NHỎ (dùng chèn vào giữa câu chữ / bảng)
# ---------------------------------------------------------------------------
def render_trend_badge(text: str, change_value) -> str:
    """Trả về đoạn HTML dạng pill nhỏ, dùng chèn trong st.markdown khác (không tự render)."""
    color = get_trend_color(change_value)
    return (
        f'<span style="background:{color}22; color:{color}; border:1px solid {color}; '
        f'padding:2px 10px; border-radius:999px; font-weight:600; font-size:.8rem;">{text}</span>'
    )


# ---------------------------------------------------------------------------
# 5. CARD PHÂN TÍCH / KHUYẾN NGHỊ — viền và chữ đổi màu theo xu hướng
# ---------------------------------------------------------------------------
def render_section_card(title: str, change_value, body_up: str, body_down: str, body_flat: str = ""):
    color = get_trend_color(change_value)
    if color == COLOR_UP:
        body = body_up
    elif color == COLOR_DOWN:
        body = body_down
    else:
        body = body_flat or body_up

    st.markdown(
        f"""
        <div style="border:1px solid {color}; border-radius:12px; padding:14px 18px;
                    background:{color}14; margin-top:12px; transition: all .2s ease;">
            <h4 style="color:{color}; margin:0 0 6px 0;">{title}</h4>
            <p style="color:{color}; font-weight:600; margin:0;">{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 6. TÔ MÀU 1 CỘT SỐ TRONG DATAFRAME (dùng với st.dataframe(df.style...))
# ---------------------------------------------------------------------------
def colorize_dataframe_column(df: pd.DataFrame, column: str):
    """
    Trả về pandas Styler: giá trị dương tô xanh, âm tô đỏ trong 1 cột chỉ định.
    Dùng: st.dataframe(colorize_dataframe_column(df, "Kỳ Vọng (%)"), use_container_width=True)
    """
    if column not in df.columns:
        return df

    def _color(val):
        c = get_trend_color(val)
        return f"color: {c}; font-weight: 600;"

    return df.style.applymap(_color, subset=[column])
