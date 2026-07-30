import streamlit as st


def _get_supabase():
    """Kết nối Supabase an toàn: thiếu secrets vẫn không làm sập app."""
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)  # cache 30 phút, không cần đọc DB liên tục
def get_market_breadth():
    """
    Đọc snapshot "sức khỏe thị trường" (breadth) MỚI NHẤT do bot nền
    (breadth_scanner.py, chạy qua GitHub Actions "Scan Breadth HOSE") ghi
    vào bảng Supabase `market_breadth`.

    Trả về None nếu:
    - Chưa cấu hình Supabase secrets, hoặc
    - Bảng `market_breadth` chưa tồn tại / chưa có dòng nào (chưa chạy bot lần nào).
    """
    sb = _get_supabase()
    if sb is None:
        return None
    try:
        resp = (
            sb.table("market_breadth")
            .select("*")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None

        row = rows[0]
        return {
            "updated_at":       row.get("updated_at", "—"),
            "n_total":          int(row.get("n_total", 0) or 0),
            "advance":          int(row.get("advance", 0) or 0),
            "decline":          int(row.get("decline", 0) or 0),
            "unchanged":        int(row.get("unchanged", 0) or 0),
            "ad_pct":           float(row.get("ad_pct", 0) or 0),
            "pct_above_ma20":   float(row.get("pct_above_ma20", 0) or 0),
            "pct_above_ma50":   float(row.get("pct_above_ma50", 0) or 0),
            "breadth_score":    int(row.get("breadth_score", 0) or 0),
            "momentum_note":    row.get("momentum_note"),
            # Các key này để tương thích với market_recommendation() trong trend_engine.py
            "total":            int(row.get("n_total", 0) or 0),
            "ad_change":        float(row.get("ad_change", 0) or 0),
        }
    except Exception:
        # Bảng chưa tồn tại / lỗi kết nối -> im lặng trả về None, main.py sẽ tự hiện
        # hướng dẫn "Vào GitHub Actions chạy Scan Breadth HOSE" thay vì làm sập app.
        return None


def render_breadth_panel(breadth: dict):
    """
    Hiển thị panel "Sức Khỏe Thị Trường" — tách riêng ra hàm này để có thể tái sử
    dụng ở nơi khác ngoài main.py nếu cần (main.py hiện tại tự vẽ inline, hàm này
    cho các tab/trang khác gọi lại mà không phải copy code).
    """
    if breadth is None:
        st.info(
            "⏳ Chưa có dữ liệu breadth. "
            "Vào **GitHub → Actions → Scan Breadth HOSE → Run workflow** để quét lần đầu."
        )
        return

    b_updated = breadth.get("updated_at", "—")
    b_total   = breadth.get("n_total", 0)
    b_ad      = breadth.get("ad_pct", 0)
    b_ma20    = breadth.get("pct_above_ma20", 0)
    b_ma50    = breadth.get("pct_above_ma50", 0)
    b_score   = breadth.get("breadth_score", 0)
    b_note    = breadth.get("momentum_note")

    st.caption(f"🕒 Cập nhật: **{b_updated}** — {b_total} mã hợp lệ")

    bb1, bb2, bb3, bb4 = st.columns(4)
    bb1.metric("📈 A/D%", f"{b_ad:.1f}%",
               delta="Tăng giá" if b_ad >= 50 else "Giảm giá",
               delta_color="normal" if b_ad >= 50 else "inverse")
    bb2.metric("📊 % trên MA20", f"{b_ma20:.1f}%")
    bb3.metric("📊 % trên MA50", f"{b_ma50:.1f}%")
    bs_color = "🟢" if b_score >= 3 else ("🔴" if b_score <= -3 else "🟡")
    bb4.metric("🎯 Breadth Score", f"{b_score:+d}", delta=f"{bs_color}")

    ad_color = "🟢" if b_ad   >= 50 else "🔴"
    ma_color = "🟢" if b_ma50 >= 50 else ("🟡" if b_ma50 >= 30 else "🔴")
    st.progress(min(max(b_ad, 0), 100)   / 100, text=f"{ad_color} A/D: {b_ad:.1f}% mã tăng giá")
    st.progress(min(max(b_ma50, 0), 100) / 100, text=f"{ma_color} Cấu trúc: {b_ma50:.1f}% mã trên MA50")

    if b_note:
        st.info(b_note)
