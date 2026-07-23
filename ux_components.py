"""
ux_components.py
----------------
File UX tổng hợp cho hệ thống Cô Tiên Stock.

Gồm:
  1. inject_smooth_ux()          -> CSS làm mượt giao diện
  2. get_trend_color()           -> quy tắc màu chuẩn: TĂNG=xanh, GIẢM=đỏ, ĐỨNG=tím
  3. render_trend_metric()       -> metric tự đổi màu
  4. render_trend_badge()        -> badge nhỏ dạng pill
  5. render_section_card()       -> card phân tích/khuyến nghị
  6. colorize_dataframe_column() -> tô màu cột số trong DataFrame
  7. setup_cache_clear_button()  -> nút xóa cache st.cache_data / st.cache_resource
  8. render_search_and_export()  -> ô tìm kiếm + nút xuất CSV cho bảng kết quả quét
"""

import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# BẢNG MÀU CHUẨN CHO TOÀN HỆ THỐNG
# ---------------------------------------------------------------------------
COLOR_UP   = "#34d399"    # xanh lá – tăng
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
# 1. CSS LÀM MƯỢT GIAO DIỆN
# ---------------------------------------------------------------------------
def inject_smooth_ux():
    """Bơm CSS giúp giao diện mượt hơn: fade-in, hover mềm, scrollbar tím, thanh loading mảnh."""
    st.markdown(
        f"""
        <style>
        div[data-testid="stVerticalBlock"] > div {{
            animation: fadeInUx 0.35s ease-in-out;
        }}
        @keyframes fadeInUx {{
            from {{ opacity: 0; transform: translateY(4px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}

        div[data-testid="stMetric"] {{
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }}
        div[data-testid="stMetric"]:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 22px rgba(109,40,217,.35);
            border-color: #6d28d9;
        }}

        .stButton > button {{
            transition: transform .15s ease, filter .15s ease, box-shadow .15s ease;
        }}
        .stButton > button:active {{ transform: scale(0.97); }}

        .stTabs [data-baseweb="tab"] {{
            transition: background .2s ease, color .2s ease;
        }}

        div[role="progressbar"] > div {{
            background: linear-gradient(90deg, #6d28d9, #34d399) !important;
        }}

        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: {COLOR_BG_PURPLE}; }}
        ::-webkit-scrollbar-thumb {{
            background: #4a3a7a; border-radius: 8px;
        }}
        ::-webkit-scrollbar-thumb:hover {{ background: #6d28d9; }}

        .stDataFrame [role="row"]:hover {{
            background: rgba(109,40,217,.12) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 2. METRIC TỰ ĐỔI MÀU
# ---------------------------------------------------------------------------
def render_trend_metric(label: str, value, change_value=None, suffix: str = "", value_fmt: str = "{:,.2f}"):
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
# 3. BADGE NHỎ
# ---------------------------------------------------------------------------
def render_trend_badge(text: str, change_value) -> str:
    color = get_trend_color(change_value)
    return (
        f'<span style="background:{color}22; color:{color}; border:1px solid {color}; '
        f'padding:2px 10px; border-radius:999px; font-weight:600; font-size:.8rem;">{text}</span>'
    )


# ---------------------------------------------------------------------------
# 4. CARD PHÂN TÍCH / KHUYẾN NGHỊ
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
# 5. TÔ MÀU CỘT SỐ TRONG DATAFRAME
# ---------------------------------------------------------------------------
def _cell_color(val) -> str:
    """
    Hàm style dùng cho pandas Styler.map() (pandas ≥ 2.1) hoặc applymap() (pandas < 2.1).
    Trả về CSS string cho từng ô.
    """
    c = get_trend_color(val)
    return f"color: {c}; font-weight: 600;"


def colorize_dataframe_column(df: pd.DataFrame, column: str):
    """
    Tô màu một cột số theo quy tắc TĂNG=xanh / GIẢM=đỏ / ĐỨNG=tím.

    Tương thích:
      - pandas ≥ 2.1 : dùng Styler.map()
      - pandas < 2.1  : dùng Styler.applymap()  (deprecated nhưng vẫn chạy)

    Cách dùng:
        styled = colorize_dataframe_column(df, "% Thay đổi")
        st.dataframe(styled, use_container_width=True)
    """
    if column not in df.columns:
        return df

    styler = df.style

    # pandas ≥ 2.1 đổi applymap -> map
    if hasattr(styler, "map"):
        styler = styler.map(_cell_color, subset=[column])
    else:
        styler = styler.applymap(_cell_color, subset=[column])

    return styler


def colorize_dataframe_columns(df: pd.DataFrame, columns: list[str]):
    """
    Tô màu NHIỀU cột cùng lúc.

    Cách dùng:
        styled = colorize_dataframe_columns(df, ["% Thay đổi", "LNST YoY", "ROE"])
        st.dataframe(styled, use_container_width=True)
    """
    valid_cols = [c for c in columns if c in df.columns]
    if not valid_cols:
        return df

    styler = df.style

    if hasattr(styler, "map"):
        styler = styler.map(_cell_color, subset=valid_cols)
    else:
        styler = styler.applymap(_cell_color, subset=valid_cols)

    return styler


# ---------------------------------------------------------------------------
# 6. NÚT XÓA CACHE  (setup_cache_clear_button)
# ---------------------------------------------------------------------------
def setup_cache_clear_button():
    """
    Hiển thị nút 🗑️ Xóa Cache trong sidebar.
    Khi bấm sẽ clear toàn bộ st.cache_data và st.cache_resource rồi rerun.
    """
    with st.sidebar:
        st.markdown("---")
        if st.button("🗑️ Xóa Cache & Tải lại", use_container_width=True):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()


# ---------------------------------------------------------------------------
# 7. Ô TÌM KIẾM + XUẤT CSV  (render_search_and_export)
# ---------------------------------------------------------------------------
def render_search_and_export(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hiển thị:
      - Ô tìm kiếm theo mã CP (lọc tức thì)
      - Nút xuất CSV toàn bộ kết quả
    Trả về DataFrame đã lọc theo từ khóa tìm kiếm.

    Dùng trong Tab 3 (Kết Quả Quét):
        df_display = render_search_and_export(raw_df)
        render_screener_results(df_display, signal_filter)
    """
    if df is None or df.empty:
        return df

    col_search, col_export = st.columns([3, 1])

    with col_search:
        keyword = st.text_input(
            "🔍 Tìm mã cổ phiếu:",
            value="",
            placeholder="Nhập mã CP (VD: FPT, HPG, VNM...)",
            key="search_ticker_tab3",
        ).upper().strip()

    with col_export:
        st.markdown("<br>", unsafe_allow_html=True)  # căn thẳng hàng với text input
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Xuất CSV",
            data=csv_bytes,
            file_name="ket_qua_quet.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Lọc theo từ khóa (khớp với cột "Mã CP" nếu có, fallback sang toàn bộ chuỗi)
    if keyword:
        ticker_col = next(
            (c for c in df.columns if c in ("Mã CP", "ticker", "symbol", "Ticker", "Symbol")),
            None,
        )
        if ticker_col:
            df = df[df[ticker_col].astype(str).str.upper().str.contains(keyword, na=False)]
        else:
            mask = df.apply(lambda col: col.astype(str).str.upper().str.contains(keyword, na=False)).any(axis=1)
            df = df[mask]

    st.caption(f"📊 Hiển thị **{len(df)}** mã" + (f" (lọc từ khóa: `{keyword}`)" if keyword else ""))

    return df
