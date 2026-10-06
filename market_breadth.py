import math
from datetime import datetime, timedelta, timezone, time as dtime

import streamlit as st

VN_TZ = timezone(timedelta(hours=7))

# Bot nền (breadth_scanner.py) chạy 1 LẦN/NGÀY sau đóng cửa: cron chính 17:30 ICT,
# cron dự phòng 18:30 ICT. Quá EXPECTED_RUN_CUTOFF mà chưa có dữ liệu hôm nay -> coi là job lỗi.
EXPECTED_RUN_CUTOFF = dtime(19, 0)
# Từ giờ này, giá đóng cửa chính thức của phiên hôm đó được coi là "đã sẵn sàng" ở nguồn dữ liệu.
DATA_READY_TIME = dtime(17, 0)

# Ngày nghỉ giao dịch rơi vào T2-T6 (Tết, 30/4, 2/9...). Điền dạng "YYYY-MM-DD".
# Có thể khai báo thêm trong secrets:  MARKET_HOLIDAYS = ["2026-09-02", ...]
VN_MARKET_HOLIDAYS = set()


def _vn_now():
    return datetime.now(VN_TZ).replace(tzinfo=None)


def _holidays():
    extra = set()
    try:
        extra = {str(x) for x in st.secrets.get("MARKET_HOLIDAYS", [])}
    except Exception:
        pass
    return VN_MARKET_HOLIDAYS | extra


def _is_trading_day(d):
    return d.weekday() < 5 and d.isoformat() not in _holidays()


def _expected_latest_trading_date(now: datetime = None):
    """Phiên gần nhất mà dữ liệu giá lẽ ra đã có: hôm nay nếu là ngày giao dịch và đã qua
    DATA_READY_TIME, ngược lại lùi về ngày giao dịch trước đó (bỏ qua cuối tuần + ngày lễ)."""
    now = now or _vn_now()
    d = now.date()
    if _is_trading_day(d) and now.time() < DATA_READY_TIME:
        d -= timedelta(days=1)
    while not _is_trading_day(d):
        d -= timedelta(days=1)
    return d


def _parse_date(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_dt(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _job_stale_today(breadth: dict, now: datetime) -> bool:
    """Chỉ cảnh báo "workflow có thể lỗi" khi: hôm nay là ngày giao dịch, đã qua
    EXPECTED_RUN_CUTOFF, mà data_date vẫn chưa phải hôm nay."""
    if not _is_trading_day(now.date()):
        return False
    if now.time() < EXPECTED_RUN_CUTOFF:
        return False
    data_date = _parse_date((breadth or {}).get("data_date"))
    if data_date is None:
        return True
    return data_date < now.date()


def breadth_freshness(breadth: dict):
    """Hai loại "chậm" độc lập:
    1) is_stale  : đã quá EXPECTED_RUN_CUTOFF mà chưa có dữ liệu phiên hôm nay -> job có thể lỗi.
    2) data_stale: bot ĐÃ chạy sau khi giá phiên kỳ vọng sẵn sàng, nhưng data_date vẫn cũ hơn
                   -> nguồn giá cập nhật chậm (khác nguyên nhân 1).
    """
    out = {"is_stale": False, "minutes_ago": None, "data_stale": False,
           "data_date": None, "expected_date": None}
    if not breadth:
        return out

    now = _vn_now()
    updated_at = _parse_dt(breadth.get("updated_at"))
    if updated_at:
        out["minutes_ago"] = max(0, round((now - updated_at).total_seconds() / 60))

    out["is_stale"] = _job_stale_today(breadth, now)

    expected = _expected_latest_trading_date(now)
    out["expected_date"] = expected
    data_date = _parse_date(breadth.get("data_date"))
    out["data_date"] = data_date
    if data_date and updated_at:
        ready_at = datetime.combine(expected, DATA_READY_TIME)
        # Chỉ coi là "nguồn giá chậm" nếu bot chạy SAU khi giá lẽ ra đã sẵn sàng
        out["data_stale"] = data_date < expected and updated_at >= ready_at
    return out


def _num(v, default=0.0, lo=None, hi=None):
    """Ép về số an toàn: None / chuỗi lạ / NaN / inf -> default."""
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
    except (TypeError, ValueError):
        return default
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return x


def _fmt_ago(minutes):
    if minutes is None:
        return ""
    if minutes < 60:
        return f"{minutes} phút trước"
    if minutes < 24 * 60:
        return f"{minutes // 60} giờ trước"
    return f"{minutes // (24 * 60)} ngày trước"


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_breadth_raw(bucket):
    """Ném ngoại lệ khi lỗi -> Streamlit KHÔNG cache lỗi (bản cũ cache None 30 phút).
    `bucket` đổi mỗi 5 phút để tránh CDN raw.githubusercontent trả bản cũ."""
    import requests

    try:
        base = str(st.secrets.get("GITHUB_RAW_BASE", "")).rstrip("/")
    except Exception:
        base = ""
    if not base:
        base = "https://raw.githubusercontent.com/nnnhutien-cpu/Fairy-stock/main"

    resp = requests.get(f"{base}/breadth.json", params={"t": bucket}, timeout=10,
                        headers={"Cache-Control": "no-cache"})
    if resp.status_code == 404:
        raise FileNotFoundError("breadth.json chưa tồn tại (bot chưa chạy lần nào)")
    resp.raise_for_status()
    resp.encoding = "utf-8"
    row = resp.json()
    if not isinstance(row, dict) or not row:
        raise ValueError("breadth.json rỗng hoặc sai định dạng")
    return row


def get_market_breadth():
    """Đọc snapshot breadth mới nhất do bot nền ghi vào breadth.json (qua raw.githubusercontent).
    Trả về None nếu chưa có file hoặc lỗi mạng (không cache kết quả lỗi)."""
    bucket = int(datetime.now().timestamp() // 300)
    try:
        row = _fetch_breadth_raw(bucket)
    except Exception:
        return None

    n_total = int(_num(row.get("n_total"), 0, lo=0))
    return {
        "updated_at":     row.get("updated_at") or "—",
        "data_date":      row.get("data_date"),
        "n_total":        n_total,
        "advance":        int(_num(row.get("advance"), 0, lo=0)),
        "decline":        int(_num(row.get("decline"), 0, lo=0)),
        "unchanged":      int(_num(row.get("unchanged"), 0, lo=0)),
        "ad_pct":         _num(row.get("ad_pct"), 0, 0, 100),
        "pct_above_ma20": _num(row.get("pct_above_ma20"), 0, 0, 100),
        "pct_above_ma50": _num(row.get("pct_above_ma50"), 0, 0, 100),
        "breadth_score":  int(_num(row.get("breadth_score"), 0)),
        "momentum_note":  row.get("momentum_note"),
        # tương thích market_recommendation() trong trend_engine.py
        "total":          n_total,
        "ad_change":      _num(row.get("ad_change"), 0),
    }


def render_breadth_panel(breadth: dict):
    """Panel "Sức Khỏe Thị Trường" (tái sử dụng được ở nhiều tab)."""
    if breadth is None:
        st.info(
            "⏳ Chưa đọc được dữ liệu breadth (bot chưa chạy lần nào, hoặc lỗi mạng tạm thời). "
            "Hệ thống quét 1 lần/ngày sau đóng cửa (~17:30-18:30 ICT, T2-T6). Lần đầu: vào "
            "**GitHub → Actions → Scan Breadth HOSE → Run workflow** (force = true) để quét ngay."
        )
        return

    fresh = breadth_freshness(breadth)
    d_date = fresh["data_date"].strftime("%d/%m/%Y") if fresh["data_date"] else "—"
    ago = _fmt_ago(fresh["minutes_ago"])
    st.caption(
        f"🕒 Bot chạy lúc: **{breadth['updated_at']}**{f' ({ago})' if ago else ''} · "
        f"📅 Dữ liệu phản ánh phiên: **{d_date}** · {breadth['n_total']} mã hợp lệ · "
        "🔁 Cập nhật 1 lần/ngày sau đóng cửa (~17:30-18:30 ICT)"
    )
    if fresh["data_stale"]:
        st.warning(
            f"⚠️ Bot đã chạy nhưng **giá lấy về vẫn thuộc phiên {d_date}** "
            f"(kỳ vọng: {fresh['expected_date']:%d/%m/%Y}) — nguồn giá có thể chưa cập nhật kịp. "
            "Bot sẽ tự lấy lại ở lượt quét kế tiếp."
        )
    if fresh["is_stale"]:
        st.warning(
            f"⚠️ Đã qua {EXPECTED_RUN_CUTOFF:%H:%M} ICT mà chưa có dữ liệu phiên hôm nay — "
            "workflow có thể đang lỗi. Kiểm tra **GitHub → Actions → Scan Breadth HOSE**."
        )

    ad, ma20, ma50, score = (breadth["ad_pct"], breadth["pct_above_ma20"],
                             breadth["pct_above_ma50"], breadth["breadth_score"])

    c1, c2, c3, c4 = st.columns(4)
    # delta hiển thị số mã tăng/giảm (trung tính) thay vì mũi tên xanh/đỏ dễ gây hiểu nhầm
    c1.metric("📈 A/D%", f"{ad:.1f}%",
              delta=f"{breadth['advance']} tăng · {breadth['decline']} giảm", delta_color="off")
    c2.metric("📊 % trên MA20", f"{ma20:.1f}%")
    c3.metric("📊 % trên MA50", f"{ma50:.1f}%")
    if score >= 3:
        c4.metric("🎯 Breadth Score", f"{score:+d}", delta="🟢 Tích cực", delta_color="off")
    elif score <= -3:
        c4.metric("🎯 Breadth Score", f"{score:+d}", delta="🔴 Tiêu cực", delta_color="off")
    else:
        c4.metric("🎯 Breadth Score", f"{score:+d}", delta="🟡 Trung tính", delta_color="off")

    ad_icon = "🟢" if ad >= 50 else "🔴"
    ma_icon = "🟢" if ma50 >= 50 else ("🟡" if ma50 >= 30 else "🔴")
    st.progress(ad / 100, text=f"{ad_icon} A/D: {ad:.1f}% mã tăng giá")
    st.progress(ma50 / 100, text=f"{ma_icon} Cấu trúc: {ma50:.1f}% mã trên MA50")

    if breadth.get("momentum_note"):
        st.info(breadth["momentum_note"])
