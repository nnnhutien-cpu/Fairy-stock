import streamlit as st
import pandas as pd

import ui_kit


def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div class="side-brand"><div class="logo">🧚‍♀️</div>'
            '<div><div class="t">CÔ TIÊN STOCK</div><div class="s">Phân tích dòng tiền & kỹ thuật</div></div></div>'
            '<div class="side-sec">Bộ lọc quét</div>',
            unsafe_allow_html=True,
        )
        exchange_choice = st.selectbox("Sàn giao dịch", ["HOSE", "HNX", "UPCOM", "Tất cả 3 sàn"])
        signal_filter = st.radio("Tín hiệu kỹ thuật", ["Tất cả", "🟢 Tích cực", "🔴 Tiêu cực"])
        max_scan = st.slider("Số mã quét tối đa", 10, 2000, 100, step=10)
        fast_mode = st.toggle(
            "⚡ Chế độ nhanh (~60 mã thanh khoản cao)",
            value=True,
            help="Ưu tiên nhóm vốn hoá lớn, thanh khoản cao -> có kết quả trong 1–3 phút."
        )
        with st.expander("🛠️ Tham số Ichimoku", expanded=False):
            c1, c2 = st.columns(2)
            p_tenkan   = c1.number_input("Tenkan", value=9,  step=1)
            p_kijun    = c2.number_input("Kijun",  value=26, step=1)
            p_senkou_b = c1.number_input("Senkou B", value=52, step=1)
            p_shift    = c2.number_input("Shift",  value=26, step=1)
        st.markdown('<div class="side-sec">Hệ thống</div>', unsafe_allow_html=True)
    return exchange_choice, signal_filter, max_scan, p_tenkan, p_kijun, p_senkou_b, p_shift, fast_mode


def render_market_tab(chart_df, df_today):
    """
    Render biểu đồ volume intraday — P/E và 4 cột phân tích do main.py xử lý.
    Header "💓 Nhịp đập thị trường" đã được main.py vẽ (qua sb_header()) ngay
    trước khi gọi hàm này — KHÔNG vẽ lại header ở đây để tránh trùng lặp.
    """
    st.caption("Thanh khoản intraday so sánh hôm nay vs hôm qua")

    if chart_df is not None and not chart_df.empty:
        st.line_chart(chart_df, color=["#8b7fb5", "#34d399"], height=380)
        st.caption("🟣 Hôm qua (tham chiếu) · 🟢 Hôm nay (real-time)")
    else:
        st.info("📡 Chưa có dữ liệu biểu đồ. Dữ liệu VN-INDEX đang được tải hoặc thị trường chưa mở phiên.")


def _filter_and_clean(results_df, signal_filter):
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame(results_df)
    if results_df.empty:
        return results_df
    if signal_filter != "Tất cả" and 'Trạng thái' in results_df.columns:
        results_df = results_df[results_df['Trạng thái'] == signal_filter]
    cols_to_use = [col for col in results_df.columns if str(col) != '9']
    return results_df[cols_to_use]


_NUM_FMT = {
    "Giá": "%.2f", "GTGD (Tỷ)": "%.1f", "Khối Lượng": "localized", "Vol x TB20": "%.2f",
    "Kijun17": "%.2f", "Knife65": "%.2f", "Knife129": "%.2f", "Cách Knife129 (%)": "%.1f%%",
    "RSI14": "%.0f", "MFI14": "%.0f",
}


def _col_config(df):
    cfg = {"Mã CP": st.column_config.TextColumn("Mã CP", pinned=True, width="small")}
    for col, fmt in _NUM_FMT.items():
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            cfg[col] = st.column_config.NumberColumn(col, format=fmt)
    return cfg


def show_table(df, height=None):
    """Bảng dữ liệu chung: số căn phải có phân tách hàng nghìn, cột Mã CP ghim trái."""
    kw = {"height": height} if height else {}
    st.dataframe(df, width="stretch", hide_index=True, column_config=_col_config(df), **kw)


def _stat_row(df):
    def cnt(col, needle):
        if col not in df.columns:
            return None
        return int(df[col].astype(str).str.contains(needle, regex=False, na=False).sum())
    items = [("Mã khớp bộ lọc", len(df), "")]
    for label, col, needle, cls in [
        ("Tích cực", "Trạng thái", "Tích cực", "val-up"),
        ("Tiêu cực", "Trạng thái", "Tiêu cực", "val-down"),
        ("Tiền vào mạnh", "Dòng Tiền", "Vào Mạnh", "val-warn"),
    ]:
        n = cnt(col, needle)
        if n is not None:
            items.append((label, n, cls))
    cells = "".join(
        f'<div class="sb-stat"><div class="sb-stat-label">{l}</div>'
        f'<div class="sb-stat-value {c}">{v}</div></div>' for l, v, c in items
    )
    st.markdown(f'<div class="sb-stat-row">{cells}</div>', unsafe_allow_html=True)


def render_screener_results(results_df, signal_filter):
    df = _filter_and_clean(results_df, signal_filter)
    if df.empty:
        st.info("Không có mã nào khớp bộ lọc hiện tại.")
        return

    _stat_row(df)

    def pick(cols):
        return [c for c in cols if c in df.columns]

    groups = {
        "📋 Tổng quan": pick([
            "Mã CP", "Giá", "GTGD (Tỷ)", "Khối Lượng", "Vol x TB20",
            "Dòng Tiền", "Xu Hướng", "Trạng thái",
        ]),
        "📐 3 đường định giá": pick([
            "Mã CP", "Giá", "Kijun17", "Knife65", "Knife129",
            "Cách Knife129 (%)", "Định Giá (129)", "Hợp Bích (65≈129)",
            "Cảnh Báo Mua Đuổi", "Ichimoku_Cloud",
        ]),
        "🗂️ Toàn bộ cột": list(df.columns),
    }
    tabs = st.tabs(list(groups.keys()))
    for tab, label in zip(tabs, groups.keys()):
        with tab:
            cols = groups[label]
            if cols:
                show_table(df[cols], height=min(38 + 35 * len(df), ui_kit.TABLE_H))
            else:
                st.caption("Không có cột dữ liệu phù hợp cho nhóm này.")


def render_screener_signals(results_df, signal_filter):
    df = _filter_and_clean(results_df, signal_filter)
    if df.empty:
        st.info("Không có mã nào khớp bộ lọc hiện tại.")
        return
    st.markdown(f"""
    <div class="sb-note">
        📡 <b>{len(df)} mã</b> — tín hiệu RSI/MFI chỉ có ý nghĩa mua/bán khi mã đang ở trạng thái Sideway.
    </div>
    """, unsafe_allow_html=True)
    cols = [c for c in [
        "Mã CP", "Giá", "Xu Hướng", "Cảnh Báo Tạo Đỉnh",
        "Tín Hiệu Bắt Đáy", "RSI14", "MFI14", "Tín Hiệu Sideway (MFI/RSI)",
    ] if c in df.columns]
    if cols:
        show_table(df[cols], height=min(38 + 35 * len(df), ui_kit.TABLE_H))
    else:
        st.info("Không có cột tín hiệu phù hợp trong dữ liệu hiện tại.")
