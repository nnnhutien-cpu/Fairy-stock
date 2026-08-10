"""
Tab "🚀 Screener Sức Bật" — Fairy-stock
========================================
Hai chế độ:
  1. TRA CỨU 1 MÃ  — gõ mã → ra ngay card chỉ số + KC/HT (không scan TT)
  2. SCAN TOÀN TT  — lọc HOSE / HNX / UPCOM theo sức bật

Lý thuyết Sức bật:
  • Sức bật  = (Độ giãn% / Số phiên giảm) × 10
              → Giảm 30% trong 15 phiên >>> giảm 30% trong 60 phiên
              → VIX, GEX, VRE bật nhanh hơn CTG, TCB cùng pha vì nén nhanh hơn
  • Độ giãn  = % drawdown từ đỉnh pha → đáy pha (toàn bộ lịch sử từ 01/2022 đến nay)

Tích hợp vào main.py:
    from screener_suc_bat import render_suc_bat_tab
    with tab_suc_bat:
        render_suc_bat_tab()
"""

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import time
import requests
import concurrent.futures as _cf

# ─────────────────────────────────────────────────────────────
#  CSS  (giữ nguyên palette tím của app)
# ─────────────────────────────────────────────────────────────
_CSS = """
<style>
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

/* Card tra cứu */
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
.val-up   { color: #00e676 !important; }
.val-down { color: #ff5252 !important; }
.val-warn { color: #ffd740 !important; }

.lk-section { font-size: 11px; color: #8b7fb5; text-transform: uppercase;
               letter-spacing: .6px; margin: 14px 0 8px;
               border-bottom: 1px solid #2c2151; padding-bottom: 4px; }

.sr-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.sr-table th { color: #666; font-weight: 400; text-align: left;
               padding: 4px 8px; font-size: 11px; text-transform: uppercase; }
.sr-table td { padding: 5px 8px; border-bottom: 1px solid #1e1a33; color: #ccc; }
.sr-table tr:last-child td { border-bottom: none; }
.badge-r { background:#3a1a1a; color:#ff5252; padding:2px 8px;
           border-radius:4px; font-size:11px; font-weight:600; }
.badge-s { background:#1a3a1a; color:#00e676; padding:2px 8px;
           border-radius:4px; font-size:11px; font-weight:600; }
.badge-fib { background:#1a1a3a; color:#7c9ef5; padding:2px 6px;
             border-radius:4px; font-size:10px; }

.formula-note {
    background: #12102a; border-left: 3px solid #a78bfa;
    padding: 10px 14px; border-radius: 0 8px 8px 0;
    font-size: 12px; color: #999; margin-top: 12px; line-height: 1.7;
}

/* scan section */
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
</style>
"""

# ─────────────────────────────────────────────────────────────
#  DATA LAYER — fallback chain DNSE → FireAnt → VCI → yfinance
# ─────────────────────────────────────────────────────────────
# DNSE đứng đầu vì hoạt động tốt nhất trên Streamlit Cloud (không bị IP block,
# không cần auth, trả JSON nhanh ~1-2s). VCI/vnstock thường bị rate-limit hoặc
# raise exception ngay → gây lỗi "0.0s" khi race timeout bị tính sai.

_DATA_START = "2022-01-01"


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _fetch_dnse(symbol: str, start: str = _DATA_START):
    """DNSE public chart API — thường hoạt động tốt trên Streamlit Cloud."""
    try:
        end        = datetime.date.today()
        start_date = datetime.datetime.strptime(start, "%Y-%m-%d").date()
        ts_from = int(datetime.datetime.combine(start_date, datetime.time()).timestamp())
        ts_to   = int(datetime.datetime.combine(end, datetime.time(23, 59, 59)).timestamp())
        url = (
            f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
            f"?from={ts_from}&to={ts_to}&symbol={symbol}&resolution=D"
        )
        hdrs = {**_BROWSER_HEADERS, "Referer": "https://dstock.dnse.com.vn/",
                "Origin": "https://dstock.dnse.com.vn"}
        r = requests.get(url, timeout=8, headers=hdrs)
        if r.status_code != 200:
            return None, None
        raw = r.json()
        if not raw or "t" not in raw or len(raw["t"]) < 20:
            return None, None
        df = pd.DataFrame({
            "time":   pd.to_datetime(raw["t"], unit="s", utc=True)
                        .tz_convert("Asia/Ho_Chi_Minh").dt.date,
            "open":   raw.get("o", raw["c"]),
            "high":   raw.get("h", raw["c"]),
            "low":    raw.get("l", raw["c"]),
            "close":  raw["c"],
            "volume": raw.get("v", [0] * len(raw["t"])),
        })
        df["close"]  = pd.to_numeric(df["close"],  errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        # DNSE có thể trả giá thực (VD: 24500) hoặc rút gọn (24.5) tuỳ endpoint
        # Chuẩn hoá: nếu median < 1000 thì nhân 1000 (đơn vị VNĐ × 1000)
        if df["close"].median() < 1000:
            for col in ("open", "high", "low", "close"):
                df[col] = df[col] * 1000
        if len(df) >= 20:
            return df, "DNSE"
    except Exception:
        pass
    return None, None


def _fetch_fireant(symbol: str, start: str = _DATA_START):
    """FireAnt API với browser headers — tăng khả năng qua được Cloudflare."""
    try:
        end        = datetime.date.today()
        start_date = datetime.datetime.strptime(start, "%Y-%m-%d").date()
        span_days  = (end - start_date).days
        url = (
            f"https://api.fireant.vn/symbols/{symbol}/historical-quotes"
            f"?startDate={start}"
            f"&endDate={end.strftime('%Y-%m-%d')}"
            f"&offset=0&limit={span_days + 20}"
        )
        hdrs = {**_BROWSER_HEADERS, "Referer": "https://fireant.vn/",
                "Origin": "https://fireant.vn"}
        r = requests.get(url, timeout=8, headers=hdrs)
        if r.status_code != 200:
            return None, None
        raw = r.json()
        if not raw:
            return None, None
        df = pd.DataFrame(raw)
        rename = {}
        for col in df.columns:
            lc = col.lower()
            if lc == "date":                       rename[col] = "time"
            elif lc == "open":                     rename[col] = "open"
            elif lc == "high":                     rename[col] = "high"
            elif lc == "low":                      rename[col] = "low"
            elif lc == "close":                    rename[col] = "close"
            elif lc in ("volume", "totalvolume"):  rename[col] = "volume"
        df.rename(columns=rename, inplace=True)
        df["close"]  = pd.to_numeric(df.get("close", 0),  errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
        if len(df) >= 20:
            return df, "FireAnt"
    except Exception:
        pass
    return None, None


def _fetch_vnstock(symbol: str, start: str = _DATA_START):
    """vnstock — thử TCBS trước (ít bị block hơn VCI trên Streamlit Cloud), rồi VCI."""
    end = datetime.date.today().strftime("%Y-%m-%d")
    for source in ("TCBS", "VCI"):
        try:
            from vnstock import Vnstock
            stock = Vnstock().stock(symbol=symbol, source=source)
            df = stock.quote.history(start=start, end=end, interval="1D")
            if df is not None and len(df) >= 20:
                df.columns = [c.lower() for c in df.columns]
                return df.reset_index(drop=True), source
        except Exception:
            continue
    return None, None


def _fetch_yfinance(symbol: str, start: str = _DATA_START):
    """yfinance với suffix .VN — fallback cuối cùng."""
    try:
        import yfinance as yf
        ticker = f"{symbol}.VN"
        end = datetime.date.today().strftime("%Y-%m-%d")
        df = yf.Ticker(ticker).history(start=start, end=end)
        if df is None or df.empty:
            return None, None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        for col in df.columns:
            if "date" in col.lower():
                df.rename(columns={col: "time"}, inplace=True)
                break
        df["close"]  = pd.to_numeric(df.get("close", 0),  errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).reset_index(drop=True)
        if len(df) >= 20:
            return df, "Yahoo"
    except Exception:
        pass
    return None, None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ohlcv(symbol: str, start: str = _DATA_START):
    """
    Fallback chain TUẦN TỰ: DNSE → FireAnt → VCI → yfinance.
    Dùng cho SCAN TOÀN THỊ TRƯỜNG — chạy tuần tự để tránh 4x request cùng lúc.
    Returns (df, source_name) hoặc (None, None).
    """
    for fn in (_fetch_dnse, _fetch_fireant, _fetch_vnstock, _fetch_yfinance):
        df, src = fn(symbol, start)
        if df is not None:
            return df, src
    return None, None


def _fetch_ohlcv_race(symbol: str, start: str = _DATA_START, race_timeout: float = 12.0):
    """Đua song song DNSE → FireAnt → VCI → yfinance, lấy nguồn về đầu tiên.

    BUG CŨ: race_timeout=3.0s quá ngắn; VCI/vnstock raise exception ngay lập tức
    (không phải timeout thật) → as_completed trả về ngay → elapsed ≈ 0.0s →
    lỗi "không lấy được dữ liệu sau 0.0s". Fix: tăng timeout + DNSE làm nguồn đầu.

    Chỉ dùng cho TRA CỨU 1 MÃ. Scan toàn thị trường dùng fetch_ohlcv() tuần tự.
    """
    fetchers = (_fetch_dnse, _fetch_fireant, _fetch_vnstock, _fetch_yfinance)
    result = (None, None)
    # Dùng context manager để executor được cleanup đúng cách
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fn, symbol, start): fn.__name__ for fn in fetchers}
        try:
            for fut in _cf.as_completed(futures, timeout=race_timeout):
                try:
                    df, src = fut.result()
                except Exception:
                    continue
                if df is not None and len(df) >= 20:
                    result = (df, src)
                    # Cancel các futures chưa chạy xong (best-effort)
                    for f in futures:
                        f.cancel()
                    break
        except _cf.TimeoutError:
            pass  # không nguồn nào kịp trả lời trong race_timeout giây
    return result


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ohlcv_fast(symbol: str, start: str = _DATA_START):
    """Bản nhanh — tra cứu 1 mã, đua 4 nguồn song song (DNSE ưu tiên)."""
    return _fetch_ohlcv_race(symbol, start)


@st.cache_data(ttl=86400, show_spinner=False)  # tên công ty gần như không đổi -> cache 1 ngày
def fetch_company_name(symbol: str) -> str:
    """Lấy tên công ty từ FireAnt (nhanh, không cần auth)."""
    try:
        url = f"https://api.fireant.vn/symbols/{symbol}"
        r = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            d = r.json()
            return d.get("companyName", "") or d.get("name", "")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────
#  TÍNH CHỈ SỐ
# ─────────────────────────────────────────────────────────────

def compute_metrics(df) -> dict:
    close  = df["close"].values.astype(float)
    high   = df["high"].values.astype(float)  if "high"   in df.columns else close.copy()
    low    = df["low"].values.astype(float)   if "low"    in df.columns else close.copy()
    volume = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(close))

    n          = len(close)
    price_now  = float(close[-1])
    pct_change = float((close[-1] - close[-2]) / close[-2] * 100) if n >= 2 else 0.0

    # Xác định pha giảm: đỉnh → đáy trong cửa sổ
    peak_idx   = int(np.argmax(high))
    sub_low    = low[peak_idx:]
    trough_idx = peak_idx + int(np.argmin(sub_low))
    phase_high = float(high[peak_idx])
    phase_low  = float(low[trough_idx])

    drop_sessions = max(trough_idx - peak_idx, 1)
    do_gian_pct   = (phase_low - phase_high) / phase_high * 100   # âm
    do_gian_abs   = abs(do_gian_pct)
    suc_bat       = round(do_gian_abs / drop_sessions * 10, 2)
    recovery_pct  = (price_now - phase_low) / phase_low * 100 if phase_low > 0 else 0.0

    diff = phase_high - phase_low

    # ── Fibonacci: 6 mức chuẩn + 2 đầu mút ──────────────────────
    # KC = phase_low  + diff × ratio  (hồi từ đáy lên)
    # HT = phase_high - diff × ratio  (kéo từ đỉnh xuống)
    FIB_RATIOS = [
        ("0%",    0.0),
        ("14.6%", 0.146),
        ("23.6%", 0.236),
        ("38.2%", 0.382),
        ("50.0%", 0.500),
        ("61.8%", 0.618),
        ("78.6%", 0.786),
        ("100%",  1.0),
    ]
    fib_levels = []
    for label, ratio in FIB_RATIOS:
        kc_price = round(phase_low  + diff * ratio, 2)
        ht_price = round(phase_high - diff * ratio, 2)
        fib_levels.append({
            "label":    f"fibo {label}",
            "kc_price": kc_price,   # kháng cự
            "ht_price": ht_price,   # hỗ trợ
        })

    return {
        "price":         round(price_now, 2),
        "pct_change":    round(pct_change, 2),
        "phase_high":    round(phase_high, 2),
        "phase_low":     round(phase_low, 2),
        "drop_sessions": drop_sessions,
        "do_gian_pct":   round(do_gian_pct, 1),
        "do_gian_abs":   round(do_gian_abs, 1),
        "suc_bat":       suc_bat,
        "recovery_pct":  round(recovery_pct, 1),
        "fib_levels":    fib_levels,   # ← format mới, không còn swing_res/swing_sup
    }


# ─────────────────────────────────────────────────────────────
#  LOOKUP UI — tra cứu 1 mã
# ─────────────────────────────────────────────────────────────

_SRC_BADGE = {
    "DNSE":    '<span class="src-badge" style="background:#1a2a1a;color:#69db7c;">DNSE</span>',
    "VCI":     '<span class="src-badge src-vci">vnstock VCI</span>',
    "FireAnt": '<span class="src-badge src-fireant">FireAnt</span>',
    "Yahoo":   '<span class="src-badge src-yahoo">Nguồn dự phòng</span>',
}

_SRC_DISPLAY_MAP = {
    "DNSE":    "DNSE",
    "VCI":     "VCI",
    "FireAnt": "FireAnt",
    "Yahoo":   "Dự phòng",
}


def _val_class(val: float, good: float, warn: float, invert: bool = False) -> str:
    """Trả về class màu dựa trên ngưỡng."""
    if invert:
        return "val-down" if val >= good else ("val-warn" if val >= warn else "val-up")
    return "val-up" if val >= good else ("val-warn" if val >= warn else "val-down")


def _render_fib_table(m: dict):
    """Vẽ bảng Fibonacci 2 cột KC / HT — gọi từ bên trong _render_lookup_card()."""
    fib = m["fib_levels"]
    price_now = m["price"]

    rows_html = ""
    for f in fib:
        kc = f["kc_price"]
        ht = f["ht_price"]

        # Highlight dòng gần giá hiện tại nhất (trong vòng 2%)
        is_near = abs(kc - price_now) / price_now < 0.02 or abs(ht - price_now) / price_now < 0.02
        row_style = "background:#1a1a3a;" if is_near else ""

        # Cùng tông màu với tiêu đề cột (đỏ = Kháng cự, xanh = Hỗ trợ).
        # Mức CHƯA bị giá vượt qua: giữ nguyên màu đậm, không gạch ngang.
        # Mức ĐÃ bị giá vượt qua (không còn ý nghĩa KC/HT nữa): gạch ngang + nhạt màu.
        kc_active = kc > price_now      # còn là kháng cự thật (giá chưa vượt qua)
        ht_active = ht < price_now      # còn là hỗ trợ thật (giá chưa thủng qua)

        kc_color = "#ff5252" if kc_active else "#7a4444"
        ht_color = "#00e676" if ht_active else "#3f7a5c"

        kc_strike = "" if kc_active else "text-decoration:line-through;"
        ht_strike = "" if ht_active else "text-decoration:line-through;"

        kc_badge = "<span style='color:#ff5252;font-size:9px;margin-left:4px;'>▲ KC</span>" if kc_active else ""
        ht_badge = "<span style='color:#00e676;font-size:9px;margin-left:4px;'>▼ HT</span>" if ht_active else ""

        # QUAN TRỌNG: không được thụt lề các dòng HTML này. Markdown coi dòng
        # thụt lề ≥4 space là code block, làm "bể mạch" render HTML giữa chừng
        # (đây chính là nguyên nhân các thẻ </td> bị in ra thành chữ thô trước đó).
        row = (
            f'<tr style="{row_style}">'
            f'<td style="color:#8b7fb5;font-size:11px;padding:5px 8px;">{f["label"]}</td>'
            f'<td style="padding:5px 8px;">'
            f'<span style="color:{kc_color};font-weight:700;{kc_strike}">{kc:,.2f}</span>{kc_badge}'
            f'</td>'
            f'<td style="padding:5px 8px;">'
            f'<span style="color:{ht_color};font-weight:700;{ht_strike}">{ht:,.2f}</span>{ht_badge}'
            f'</td>'
            f'</tr>'
        )
        rows_html += row

    table_html = (
        '<div class="lk-section">📐 Fibonacci Retracement (đỉnh pha → đáy pha)</div>'
        '<table class="sr-table" style="width:100%;border-collapse:collapse;">'
        '<thead><tr>'
        '<th style="color:#555;font-size:11px;padding:4px 8px;text-align:left;">Mức Fibo</th>'
        '<th style="color:#ff5252;font-size:11px;padding:4px 8px;text-align:left;font-weight:700;">🔴 KHÁNG CỰ</th>'
        '<th style="color:#00e676;font-size:11px;padding:4px 8px;text-align:left;font-weight:700;">🟢 HỖ TRỢ</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '<div style="font-size:10px;color:#555;margin-top:6px;padding:0 8px;">'
        f'Giá hiện tại: <b style="color:#e0e0ff;">{price_now:,.2f}</b> &nbsp;|&nbsp; '
        f'Đỉnh pha: <b style="color:#ff5252;">{m["phase_high"]:,.2f}</b> &nbsp;|&nbsp; '
        f'Đáy pha: <b style="color:#00e676;">{m["phase_low"]:,.2f}</b>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _render_lookup_card(symbol: str, company: str, m: dict, source: str, elapsed: float | None = None):
    pct  = m["pct_change"]
    pc   = "val-up" if pct >= 0 else "val-down"
    ps   = "+" if pct >= 0 else ""
    dg_c = _val_class(m["do_gian_abs"], 30, 20, invert=True)   # sâu hơn = tốt hơn cho sức bật
    sb_c = _val_class(m["suc_bat"],     2.0, 1.0)

    src_html = _SRC_BADGE.get(source, f'<span class="src-badge">{source}</span>')

    speed_html = ""
    if elapsed is not None:
        speed_color = "#00e676" if elapsed <= 2 else ("#ffd740" if elapsed <= 4 else "#ff5252")
        speed_html = (f'<span class="src-badge" style="background:#12102a;color:{speed_color};">'
                      f'⚡ {elapsed:.1f}s</span>')

    # header
    st.markdown(f"""
    <div class="lk-card">
      <div class="lk-ticker">{symbol} {src_html}{speed_html}</div>
      <div class="lk-company">{company or "—"} · phân tích toàn bộ dữ liệu từ 01/2022 đến nay</div>
      <div class="lk-grid">
        <div class="lk-metric">
          <div class="lk-label">Giá hiện tại</div>
          <div class="lk-value">{m['price']:,.1f}</div>
          <div class="lk-sub">nghìn đồng</div>
        </div>
        <div class="lk-metric">
          <div class="lk-label">% Thay đổi</div>
          <div class="lk-value {pc}">{ps}{pct:.2f}%</div>
          <div class="lk-sub">phiên hôm nay</div>
        </div>
        <div class="lk-metric">
          <div class="lk-label">Độ giãn</div>
          <div class="lk-value {dg_c}">{m['do_gian_pct']:.1f}%</div>
          <div class="lk-sub">đỉnh → đáy pha</div>
        </div>
        <div class="lk-metric">
          <div class="lk-label">Sức bật</div>
          <div class="lk-value {sb_c}">{m['suc_bat']:.2f}</div>
          <div class="lk-sub">{m['do_gian_abs']:.1f}% / {m['drop_sessions']} phiên × 10</div>
        </div>
      </div>
      <div class="lk-grid">
        <div class="lk-metric">
          <div class="lk-label">Đỉnh pha</div>
          <div class="lk-value">{m['phase_high']:,.1f}</div>
        </div>
        <div class="lk-metric">
          <div class="lk-label">Đáy pha</div>
          <div class="lk-value">{m['phase_low']:,.1f}</div>
        </div>
        <div class="lk-metric">
          <div class="lk-label">Đã hồi</div>
          <div class="lk-value val-up">+{m['recovery_pct']:.1f}%</div>
          <div class="lk-sub">từ đáy</div>
        </div>
        <div class="lk-metric">
          <div class="lk-label">Phiên giảm</div>
          <div class="lk-value val-down">{m['drop_sessions']}</div>
          <div class="lk-sub">đỉnh → đáy</div>
        </div>
      </div>
    """, unsafe_allow_html=True)

    _render_fib_table(m)

    st.markdown("</div>", unsafe_allow_html=True)


def render_lookup_section():
    """Phần tra cứu 1 mã — hiển thị đầu tab."""
    st.markdown("### 🔎 Tra cứu nhanh 1 mã")

    col_inp, col_btn = st.columns([3, 1])
    with col_inp:
        symbol_input = st.text_input(
            "Nhập mã cổ phiếu",
            placeholder="VD: VIX, GEX, DGW, VRE...",
            label_visibility="collapsed",
            key="sb_lookup_input",
        ).upper().strip()
    with col_btn:
        lookup_btn = st.button("📊 Tra cứu", use_container_width=True, key="sb_lookup_btn")

    if not (lookup_btn or symbol_input) and "sb_lookup_result" not in st.session_state:
        st.caption("Gõ mã → Enter hoặc nhấn **Tra cứu** để xem ngay. Không cần scan toàn thị trường.")
        return

    # Trigger khi Enter (symbol thay đổi) hoặc nhấn nút
    trigger = lookup_btn or (
        symbol_input and symbol_input != st.session_state.get("sb_lookup_last", "")
    )

    if trigger and symbol_input:
        st.session_state["sb_lookup_last"] = symbol_input
        _t0 = time.time()
        with st.spinner(f"⚡ Đang đua 3 nguồn dữ liệu cho {symbol_input}…"):
            # Lấy giá + tên công ty SONG SONG, và bản thân việc lấy giá cũng
            # đua song song cả 3 nguồn (fetch_ohlcv_fast) — không còn chờ
            # tuần tự VCI → FireAnt → yfinance như bản scan toàn thị trường.
            with _cf.ThreadPoolExecutor(max_workers=2) as ex:
                fut_ohlcv = ex.submit(fetch_ohlcv_fast, symbol_input)
                fut_name  = ex.submit(fetch_company_name, symbol_input)
                df, src   = fut_ohlcv.result()
                company   = fut_name.result()
        _elapsed = time.time() - _t0
        if df is None or len(df) < 20:
            st.error(f"❌ Không lấy được dữ liệu cho **{symbol_input}** sau {_elapsed:.1f}s "
                     "(cả 3 nguồn đều không phản hồi kịp). Kiểm tra lại mã hoặc thử lại sau.")
            st.session_state.pop("sb_lookup_result", None)
            return
        # Pha giảm/hồi (sức bật) được xác định trên TOÀN BỘ lịch sử từ 01/2022
        # đến nay — không còn cắt về 120 phiên gần nhất như trước.
        metrics = compute_metrics(df)
        st.session_state["sb_lookup_result"] = {
            "symbol":  symbol_input,
            "company": company,
            "metrics": metrics,
            "source":  src,
            "elapsed": round(_elapsed, 1),
        }

    result = st.session_state.get("sb_lookup_result")
    if result:
        _render_lookup_card(
            result["symbol"],
            result["company"],
            result["metrics"],
            result["source"],
            result.get("elapsed"),
        )

    st.divider()


# ─────────────────────────────────────────────────────────────
#  SCAN TOÀN THỊ TRƯỜNG — giữ nguyên logic cũ, bổ sung fallback
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_symbols(exchanges: list) -> list:
    """Lấy danh sách mã theo sàn — thử lần lượt 3 nguồn (vci/kbs/tcbs) và
    3 cách gọi API (Vnstock 4.x / listing_companies 3.x / Listing api mới),
    đúng logic đã chứng minh hoạt động trong breadth_scanner.py (lấy được
    403 mã HOSE thành công)."""
    symbols = []

    def _get_listing_df(src):
        try:
            from vnstock import Vnstock
            obj = Vnstock(source=src).stock(symbol='VNM', exchange='HOSE')
            return obj.listing.symbols_by_exchange()
        except Exception:
            pass
        try:
            from vnstock import listing_companies
            return listing_companies()
        except Exception:
            pass
        try:
            from vnstock.api.listing import Listing
            return Listing(source=src).symbols_by_exchange()
        except Exception:
            pass
        return None

    for src in ['vci', 'kbs', 'tcbs']:
        try:
            df = _get_listing_df(src)
            if df is None or df.empty:
                continue

            df.columns = [str(c).lower().strip() for c in df.columns]

            type_col = next((c for c in df.columns if 'type' in c), None)
            if type_col:
                df = df[df[type_col].astype(str).str.upper().isin(
                    ['STOCK', 'CP', 'CỔ PHIẾU', 'EQ', 'EQUITY']
                )]

            if 'exchange' in df.columns:
                ex_map = {"HOSE": ["HOSE", "HSX"], "HNX": ["HNX"], "UPCOM": ["UPCOM"]}
                wanted = set()
                for ex in exchanges:
                    wanted.update(ex_map.get(ex, [ex]))
                df = df[df['exchange'].astype(str).str.upper().isin(wanted)]

            col = next((c for c in ['symbol', 'ticker', 'code'] if c in df.columns), None)
            if col:
                tickers = [str(t).strip().upper() for t in df[col].dropna() if str(t).strip()]
                if tickers:
                    symbols = tickers
                    break
        except Exception:
            continue

    if not symbols:
        st.warning("Không lấy được danh sách mã từ bất kỳ nguồn nào (vci/kbs/tcbs đều lỗi).")

    return list(set(symbols))


def _compute_symbol_scan(symbol: str) -> dict | None:
    """Tính chỉ số cho 1 mã trong batch scan, dùng fallback chain.

    Pha giảm/hồi được xác định trên TOÀN BỘ lịch sử từ 01/2022 đến nay mà
    fetch_ohlcv trả về — không còn cắt về n phiên gần nhất.
    """
    df, src = fetch_ohlcv(symbol)
    if df is None or len(df) < 20:
        return None
    try:
        m = compute_metrics(df)
        close  = df["close"].values.astype(float)
        volume = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(close))

        # NOTE: sr_levels (vùng KC/HT theo volume profile) chưa được tính ở đây
        # trong bản gốc — để trống nhằm tránh NameError, không phải phần Fibonacci.
        sr_levels = []

        return {
            "symbol":        symbol,
            "source":        src,
            "price":         m["price"],
            "drawdown_pct":  m["do_gian_pct"],
            "speed_pday":    round(m["do_gian_pct"] / m["drop_sessions"], 4) if m["drop_sessions"] else 0,
            "recovery_pct":  m["recovery_pct"],
            "suc_bat":       m["suc_bat"],
            "do_gian_abs":   m["do_gian_abs"],
            "drop_sessions": m["drop_sessions"],
            "phase_high":    m["phase_high"],
            "phase_low":     m["phase_low"],
            "sr_levels":     sr_levels,
            "_drawdown_abs": m["do_gian_abs"] / 100,
            "_speed_abs":    abs(m["do_gian_pct"] / m["drop_sessions"]) / 100 if m["drop_sessions"] else 0,
        }
    except Exception:
        return None


@st.cache_data(ttl=1800)
def _vnindex_drawdown() -> float:
    df, _ = fetch_ohlcv("VNINDEX")
    if df is None or df.empty:
        return 0.01
    close = df["close"].values.astype(float)
    peak  = close.max()
    now   = close[-1]
    dd    = abs((now - peak) / peak)
    return dd if dd > 0 else 0.01


def scan_all(
    symbols: list,
    batch_delay: float = 0.12,
    progress_bar=None,
    status_text=None,
) -> pd.DataFrame:
    vn_dd   = _vnindex_drawdown()
    results = []
    total   = len(symbols)

    for i, sym in enumerate(symbols):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Đang quét {sym}… ({i+1}/{total})")
        if status_text:
            status_text.text(f"⏳ {sym}")

        row = _compute_symbol_scan(sym)
        if row:
            beta = row["_drawdown_abs"] / vn_dd if vn_dd > 0 else 1.0
            row["beta_dd"]       = round(beta, 2)
            row["suc_bat_score"] = round(row["_drawdown_abs"] * beta * 100, 2)
            row["do_gian_score"] = round(row["_speed_abs"]    * beta * 1000, 2)
            results.append(row)
        time.sleep(batch_delay)

    df = pd.DataFrame(results)
    if df.empty:
        return df

    for col in ["suc_bat_score", "do_gian_score", "recovery_pct"]:
        if col in df.columns:
            df[f"{col}_rank"] = df[col].rank(pct=True).mul(100).round(1)

    df["tong_score"] = (
        df.get("suc_bat_score_rank", 0) * 0.5 +
        df.get("do_gian_score_rank", 0) * 0.3 +
        df.get("recovery_pct_rank",  0) * 0.2
    ).round(1)

    df.sort_values("tong_score", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ─────────────────────────────────────────────────────────────
#  SCAN UI helpers
# ─────────────────────────────────────────────────────────────

def _sr_str(sr_levels: list) -> str:
    kc = [f"{p}" for p, v, r in sr_levels if r == "KC"]
    ht = [f"{p}" for p, v, r in sr_levels if r == "HT"]
    parts = []
    if kc: parts.append("KC: " + " / ".join(kc[:2]))
    if ht: parts.append("HT: " + " / ".join(ht[:2]))
    return " | ".join(parts) if parts else "—"


def render_scan_section():
    """Phần scan toàn thị trường — bên dưới lookup."""
    st.markdown("### 🔍 Scan toàn thị trường")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        exchanges = st.multiselect(
            "Sàn giao dịch", ["HOSE", "HNX", "UPCOM"], default=["HOSE"])
    with col2:
        top_n = st.number_input("Hiển thị Top", min_value=10, max_value=200, value=50, step=10)
    with col3:
        min_dd = st.number_input("DD tối thiểu (%)", min_value=5, max_value=60, value=15)

    col_a, col_b = st.columns([1, 2])
    with col_a:
        run_btn = st.button("▶ Bắt đầu Scan", use_container_width=True,
                            type="primary", key="sb_scan_btn")
    with col_b:
        st.caption("⏱️ Dữ liệu tải từ 01/2022 đến nay, pha giảm/hồi tính trên toàn bộ lịch sử · "
                   "HOSE ~700 mã ≈ 5–10 phút | HNX+UPCOM thêm ~800 mã. Nên chọn 1 sàn trước.")

    cache_key = f"suc_bat_df_{','.join(sorted(exchanges))}"

    if run_btn:
        if not exchanges:
            st.warning("Chọn ít nhất 1 sàn.")
            return
        symbols = get_all_symbols(exchanges)
        if not symbols:
            st.error("Không lấy được danh sách mã. Kiểm tra kết nối vnstock.")
            return

        st.info(f"📋 Tổng {len(symbols)} mã — bắt đầu quét…")
        prog   = st.progress(0)
        status = st.empty()
        df = scan_all(symbols, batch_delay=0.12,
                      progress_bar=prog, status_text=status)
        st.session_state[cache_key] = df
        prog.empty(); status.empty()

    df: pd.DataFrame = st.session_state.get(cache_key, pd.DataFrame())
    if df.empty:
        st.info("Nhấn **▶ Bắt đầu Scan** để quét.")
        return

    df_show = df[df["drawdown_pct"] <= -abs(min_dd)].head(top_n).copy()

    # Summary
    st.markdown(f"""
    <div class="sb-stat-row">
        <div class="sb-stat">
            <div class="sb-stat-label">Mã đủ điều kiện</div>
            <div class="sb-stat-value">{len(df_show)}</div>
        </div>
        <div class="sb-stat">
            <div class="sb-stat-label">DD TB top 10</div>
            <div class="sb-stat-value" style="color:#ff5252">
                {df_show['drawdown_pct'].head(10).mean():.1f}%
            </div>
        </div>
        <div class="sb-stat">
            <div class="sb-stat-label">Hồi TB top 10</div>
            <div class="sb-stat-value" style="color:#00e676">
                +{df_show['recovery_pct'].head(10).mean():.1f}%
            </div>
        </div>
        <div class="sb-stat">
            <div class="sb-stat-label">Beta DD TB top 10</div>
            <div class="sb-stat-value" style="color:#ffd740">
                {df_show['beta_dd'].head(10).mean():.2f}x
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Bảng
    display_cols = {
        "symbol":       "Mã",
        "source":       "Nguồn",
        "price":        "Giá",
        "drawdown_pct": "Độ giãn%",
        "suc_bat":      "Sức bật",
        "drop_sessions":"Phiên giảm",
        "beta_dd":      "Beta DD",
        "recovery_pct": "Hồi%",
        "tong_score":   "⭐ Score",
    }
    df_table = df_show[list(display_cols.keys())].rename(columns=display_cols).copy()
    df_table["Nguồn"] = df_table["Nguồn"].map(_SRC_DISPLAY_MAP).fillna(df_table["Nguồn"])

    def _style(df_s):
        styles = pd.DataFrame("", index=df_s.index, columns=df_s.columns)
        if "Độ giãn%" in df_s.columns:
            styles["Độ giãn%"] = df_s["Độ giãn%"].apply(
                lambda v: "color:#ff5252;font-weight:700" if v < -30
                else ("color:#ff8a65" if v < -20 else "color:#ffcc80"))
        if "Sức bật" in df_s.columns:
            styles["Sức bật"] = df_s["Sức bật"].apply(
                lambda v: "color:#00e676;font-weight:800" if v >= 2
                else ("color:#ffd740;font-weight:700" if v >= 1 else "color:#ff5252"))
        if "Hồi%" in df_s.columns:
            styles["Hồi%"] = df_s["Hồi%"].apply(
                lambda v: "color:#00e676;font-weight:700" if v > 10
                else ("color:#69db7c" if v > 5 else "color:#aaa"))
        if "⭐ Score" in df_s.columns:
            styles["⭐ Score"] = df_s["⭐ Score"].apply(
                lambda v: "color:#00e676;font-weight:800" if v >= 70
                else ("color:#ffd740;font-weight:700" if v >= 40 else "color:#ff5252"))
        return styles

    styled = df_table.style.apply(_style, axis=None).format({
        "Giá":        "{:,.2f}",
        "Độ giãn%":   "{:.1f}%",
        "Sức bật":    "{:.2f}",
        "Beta DD":    "{:.2f}x",
        "Hồi%":       "+{:.1f}%",
        "⭐ Score":    "{:.0f}",
    })
    st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

    # Chi tiết KC/HT
    st.markdown("---")
    st.markdown("#### 🎯 Vùng Kháng Cự / Hỗ Trợ (Volume Profile)")
    selected_sym = st.selectbox("Chọn mã xem chi tiết",
                                options=df_show["symbol"].tolist(),
                                key="sb_sr_select")
    row = df_show[df_show["symbol"] == selected_sym].iloc[0]
    sr  = row.get("sr_levels", [])
    if sr:
        kc_list = [(p, v) for p, v, r in sr if r == "KC"]
        ht_list = [(p, v) for p, v, r in sr if r == "HT"]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🔴 Kháng cự**")
            for p, v in kc_list:
                st.markdown(
                    f"<span style='color:#ff5252;font-weight:700'>{p:,.2f}</span>"
                    f" &nbsp; vol: <span style='color:#aaa'>{v:.1f}%</span>",
                    unsafe_allow_html=True)
        with c2:
            st.markdown("**🟢 Hỗ trợ**")
            for p, v in ht_list:
                st.markdown(
                    f"<span style='color:#00e676;font-weight:700'>{p:,.2f}</span>"
                    f" &nbsp; vol: <span style='color:#aaa'>{v:.1f}%</span>",
                    unsafe_allow_html=True)
    else:
        st.info("Không có dữ liệu KC/HT cho mã này.")

    # Export
    st.markdown("---")
    csv = df_show.drop(
        columns=["sr_levels", "_drawdown_abs", "_speed_abs"], errors="ignore"
    ).to_csv(index=False)
    st.download_button(
        "⬇️ Tải kết quả CSV", data=csv,
        file_name=f"suc_bat_{datetime.date.today()}.csv",
        mime="text/csv",
    )
    st.caption(
        f"Dữ liệu: tổng hợp đa nguồn (từ 01/2022 đến nay), tự động chọn nguồn nhanh nhất còn hoạt động · "
        f"pha giảm/hồi tính trên toàn bộ lịch sử · Cập nhật: {datetime.date.today().strftime('%d/%m/%Y')} · "
        "Không phải khuyến nghị đầu tư"
    )


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────

def render_suc_bat_tab():
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div class="sb-header">
        <div>
            <div class="sb-title">🚀 Screener Sức Bật</div>
            <div class="sb-sub">
                Lọc cổ phiếu giảm sâu – giảm nhanh – tiềm năng bật mạnh hơn thị trường
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="sb-note">
        ⚠️ Screener này áp dụng cho <b>giai đoạn đầu sóng hồi</b> (T7/2026).
        Về sau cần kết hợp Volume + Ichimoku — không áp dụng mãi.
    </div>
    """, unsafe_allow_html=True)

    # 1. Tra cứu 1 mã (luôn hiện trên đầu)
    render_lookup_section()

    # 2. Scan toàn thị trường (bên dưới)
    render_scan_section()
