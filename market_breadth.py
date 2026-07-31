import streamlit as st
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def _vn_now():
    return datetime.now(VN_TZ).replace(tzinfo=None)


def _is_market_hours(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    morning = (t >= datetime.strptime("09:00", "%H:%M").time()) and (t <= datetime.strptime("11:30", "%H:%M").time())
    afternoon = (t >= datetime.strptime("13:00", "%H:%M").time()) and (t <= datetime.strptime("15:40", "%H:%M").time())
    return morning or afternoon


def _expected_latest_trading_date(now: datetime = None):
    """Cùng quy tắc với data_loader.py: đóng cửa 15h, dữ liệu sẵn sàng chậm nhất 17h."""
    if now is None:
        now = _vn_now()
    d = now.date()
    if now.weekday() < 5 and now.time() < datetime.strptime("17:00", "%H:%M").time():
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def breadth_freshness(breadth: dict, max_staleness_minutes: int = 45):
    """
    Kiểm tra 2 loại "chậm" khác nhau, độc lập với nhau:
    1) job_stale: bot nền (script chạy) đã lâu chưa chạy lại (>max_staleness_minutes
       trong giờ giao dịch) -> workflow có thể đang lỗi.
    2) data_stale: bot CÓ chạy đúng giờ, nhưng giá lấy về bên trong (data_date)
       vẫn là phiên cũ (nguồn VCI/MSN chưa cập nhật) -> đây là lỗi đã gặp hôm nay,
       khác hẳn (1), nên tách riêng để cảnh báo đúng nguyên nhân.
    Ngoài giờ giao dịch thì không cảnh báo job_stale (dữ liệu cuối phiên là hợp lệ).
    """
    out = {"is_stale": False, "minutes_ago": None, "data_stale": False, "data_date": None, "expected_date": None}
    if not breadth or not breadth.get("updated_at"):
        return out

    now = _vn_now()
    try:
        updated_at = datetime.strptime(breadth["updated_at"], "%Y-%m-%d %H:%M:%S")
        minutes_ago = (now - updated_at).total_seconds() / 60
        out["minutes_ago"] = round(minutes_ago)
        out["is_stale"] = _is_market_hours(now) and minutes_ago > max_staleness_minutes
    except Exception:
        pass

    expected_date = _expected_latest_trading_date(now)
    out["expected_date"] = expected_date
    data_date_str = breadth.get("data_date")
    if data_date_str:
        try:
            data_date = datetime.strptime(data_date_str, "%Y-%m-%d").date()
            out["data_date"] = data_date
            out["data_stale"] = data_date < expected_date
        except Exception:
            pass

    return out


@st.cache_data(ttl=1800, show_spinner=False)  # cache 30 phút
def get_market_breadth():
    """
    Đọc snapshot "sức khỏe thị trường" (breadth) MỚI NHẤT do bot nền
    (breadth_scanner.py, chạy qua GitHub Actions "Scan Breadth HOSE") ghi
    ra file `breadth.json` và commit thẳng vào repo. App đọc file này qua
    raw.githubusercontent.com — KHÔNG cần Supabase / secrets.

    Trả về None nếu chưa chạy bot lần nào (file chưa tồn tại) hoặc lỗi mạng.
    """
    import requests

    try:
        base = st.secrets.get("GITHUB_RAW_BASE", "").rstrip("/")
    except Exception:
        base = ""
    if not base:
        base = "https://raw.githubusercontent.com/nnnhutien-cpu/Fairy-stock/main"

    url = f"{base}/breadth.json"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return None
        row = resp.json()
    except Exception:
        return None

    if not row:
        return None

    return {
        "updated_at":       row.get("updated_at", "—"),
        "data_date":        row.get("data_date"),
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


def render_breadth_panel(breadth: dict):
    """
    Hiển thị panel "Sức Khỏe Thị Trường" — tách riêng ra hàm này để có thể tái sử
    dụng ở nơi khác ngoài main.py nếu cần (main.py hiện tại tự vẽ inline, hàm này
    cho các tab/trang khác gọi lại mà không phải copy code).
    """
    if breadth is None:
        st.info(
            "⏳ Chưa có dữ liệu breadth. Hệ thống sẽ tự động quét mỗi 30 phút trong giờ "
            "giao dịch (9h-11h30, 13h-15h40, T2-T6). Nếu đây là lần đầu chạy, vào "
            "**GitHub → Actions → Scan Breadth HOSE → Run workflow** để quét ngay."
        )
        return

    b_updated = breadth.get("updated_at", "—")
    b_total   = breadth.get("n_total", 0)
    b_ad      = breadth.get("ad_pct", 0)
    b_ma20    = breadth.get("pct_above_ma20", 0)
    b_ma50    = breadth.get("pct_above_ma50", 0)
    b_score   = breadth.get("breadth_score", 0)
    b_note    = breadth.get("momentum_note")

    fresh = breadth_freshness(breadth)
    d_date_str = fresh["data_date"].strftime("%d/%m/%Y") if fresh["data_date"] else "—"
    st.caption(
        f"🕒 Bot chạy lúc: **{b_updated}** · 📅 Dữ liệu giá phản ánh phiên: **{d_date_str}** "
        f"— {b_total} mã hợp lệ · 🔁 Tự động quét mỗi ~10-30 phút trong giờ giao dịch"
    )
    if fresh["data_stale"]:
        st.warning(
            f"⚠️ Bot chạy đúng giờ nhưng **giá lấy về vẫn thuộc phiên {d_date_str}** "
            f"(kỳ vọng: {fresh['expected_date']:%d/%m/%Y}) — nguồn dữ liệu giá (VCI/MSN) "
            "có thể chưa cập nhật kịp. Bot sẽ tự lấy lại ở lượt quét kế tiếp."
        )
    if fresh["is_stale"]:
        st.warning(
            f"⚠️ Bot quét nền chưa chạy lại trong **{fresh['minutes_ago']} phút** dù đang trong giờ giao dịch — "
            "có thể workflow đang gặp lỗi. Kiểm tra **GitHub → Actions → Scan Breadth HOSE**."
        )

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
