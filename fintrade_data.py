"""
fintrade_tab.py
---------------
UI component hiển thị dữ liệu FiinTrade Methodology trong Streamlit.
Đặt file này cùng cấp với app.py.

Cách dùng trong app.py:
    from fintrade_tab import render_fintrade_section
    render_fintrade_section()
"""

import json
import streamlit as st
from fintrade_loader import (
    get_scoring_criteria,
    get_ranking_factors,
    get_technical_indicators,
    get_ranking_data,
    get_scoring_data,
    get_technical_data,
    files_available,
)


# ── CSS tuỳ chỉnh cho phần FiinTrade ────────────────────────────────────────
_CSS = """
<style>
.fintrade-header {
    background: linear-gradient(135deg, #1a3a5c 0%, #0d6efd 100%);
    padding: 16px 20px;
    border-radius: 10px;
    margin-bottom: 20px;
    color: white;
}
.fintrade-header h3 { margin: 0; font-size: 1.2rem; }
.fintrade-header p  { margin: 4px 0 0; font-size: 0.85rem; opacity: 0.85; }

.fintrade-card {
    background: #f8f9fa;
    border-left: 4px solid #0d6efd;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.fintrade-card h4 { margin: 0 0 6px; color: #1a3a5c; font-size: 1rem; }
.fintrade-card p  { margin: 0; font-size: 0.88rem; color: #444; }

.score-badge {
    display: inline-block;
    background: #0d6efd;
    color: white;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-left: 8px;
}
.tag {
    display: inline-block;
    background: #e8f0fe;
    color: #1a3a5c;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.78rem;
    margin: 2px 2px 0 0;
}
.warn-box {
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 6px;
    padding: 12px;
    font-size: 0.88rem;
    color: #664d03;
}
</style>
"""


# ── Render từng sub-tab ──────────────────────────────────────────────────────

def _render_scoring(data: dict):
    """Hiển thị scoring methodology."""
    if not data:
        st.markdown('<div class="warn-box">⚠️ Không tìm thấy file scoring methodology.</div>', unsafe_allow_html=True)
        return

    criteria = get_scoring_criteria()

    # Nếu có danh sách tiêu chí → hiển thị dạng card
    if criteria:
        st.caption(f"Tổng cộng **{len(criteria)}** tiêu chí chấm điểm")
        for item in criteria:
            if isinstance(item, dict):
                name   = item.get("name") or item.get("criteriaName") or item.get("title") or str(item)
                desc   = item.get("description") or item.get("desc") or item.get("definition") or ""
                weight = item.get("weight") or item.get("score") or item.get("maxScore") or ""
                badge  = f'<span class="score-badge">Trọng số: {weight}</span>' if weight else ""
                tags   = item.get("category") or item.get("group") or ""
                tag_html = f'<span class="tag">{tags}</span>' if tags else ""
                st.markdown(
                    f'<div class="fintrade-card">'
                    f'  <h4>{name} {badge}</h4>'
                    f'  {tag_html}'
                    f'  <p>{desc}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        # Fallback: hiển thị raw JSON đẹp
        st.json(data)


def _render_ranking(data: dict):
    """Hiển thị ranking methodology."""
    if not data:
        st.markdown('<div class="warn-box">⚠️ Không tìm thấy file ranking methodology.</div>', unsafe_allow_html=True)
        return

    factors = get_ranking_factors()

    if factors:
        st.caption(f"Tổng cộng **{len(factors)}** yếu tố xếp hạng")
        for item in factors:
            if isinstance(item, dict):
                name  = item.get("name") or item.get("factorName") or item.get("title") or str(item)
                desc  = item.get("description") or item.get("desc") or item.get("definition") or ""
                wt    = item.get("weight") or item.get("weightPercent") or ""
                badge = f'<span class="score-badge">{wt}%</span>' if wt else ""
                st.markdown(
                    f'<div class="fintrade-card">'
                    f'  <h4>{name} {badge}</h4>'
                    f'  <p>{desc}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.json(data)


def _render_technical(data: dict):
    """Hiển thị technical analysis methodology."""
    if not data:
        st.markdown('<div class="warn-box">⚠️ Không tìm thấy file technical analysis methodology.</div>', unsafe_allow_html=True)
        return

    indicators = get_technical_indicators()

    if indicators:
        # Nhóm theo category nếu có
        categories: dict[str, list] = {}
        for item in indicators:
            if isinstance(item, dict):
                cat = item.get("category") or item.get("group") or item.get("type") or "Khác"
                categories.setdefault(cat, []).append(item)
            else:
                categories.setdefault("Khác", []).append(item)

        for cat, items in categories.items():
            st.markdown(f"##### 📌 {cat}")
            cols = st.columns(2)
            for i, item in enumerate(items):
                name = item.get("name") or item.get("indicator") or item.get("title") or str(item)
                desc = item.get("description") or item.get("desc") or item.get("formula") or ""
                signal = item.get("signal") or item.get("interpretation") or ""
                with cols[i % 2]:
                    st.markdown(
                        f'<div class="fintrade-card">'
                        f'  <h4>{name}</h4>'
                        f'  <p>{desc}</p>'
                        + (f'  <p>📈 <b>Tín hiệu:</b> {signal}</p>' if signal else "") +
                        f'</div>',
                        unsafe_allow_html=True,
                    )
    else:
        st.json(data)


# ── Hàm chính gọi từ app.py ──────────────────────────────────────────────────

def render_fintrade_section():
    """
    Render toàn bộ section FiinTrade trong tab Fairy Stock.
    Gọi hàm này bên trong tab tương ứng trong app.py.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    # Header
    st.markdown(
        '<div class="fintrade-header">'
        '  <h3>📊 FiinTrade Methodology</h3>'
        '  <p>Phương pháp luận xếp hạng, chấm điểm và phân tích kỹ thuật từ FiinTrade</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Kiểm tra file
    avail = files_available()
    missing = [k for k, v in avail.items() if not v]
    if missing:
        st.warning(
            f"⚠️ Thiếu file: **{', '.join(missing)}**. "
            "Kiểm tra đường dẫn `extenal/FiinTrade/FiinTrade-Methodology-main/`"
        )

    # 3 sub-tab
    tab_scoring, tab_ranking, tab_technical = st.tabs([
        "🏅 Chấm điểm (Scoring)",
        "🏆 Xếp hạng (Ranking)",
        "📉 Phân tích kỹ thuật",
    ])

    with tab_scoring:
        st.markdown("#### Tiêu chí chấm điểm FiinTrade")
        _render_scoring(get_scoring_data())

    with tab_ranking:
        st.markdown("#### Yếu tố xếp hạng FiinTrade")
        _render_ranking(get_ranking_data())

    with tab_technical:
        st.markdown("#### Chỉ số phân tích kỹ thuật FiinTrade")
        _render_technical(get_technical_data())

    # Nút xem JSON gốc (expander)
    with st.expander("🔍 Xem dữ liệu JSON gốc"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.caption("Scoring")
            st.json(get_scoring_data())
        with col2:
            st.caption("Ranking")
            st.json(get_ranking_data())
        with col3:
            st.caption("Technical")
            st.json(get_technical_data())
