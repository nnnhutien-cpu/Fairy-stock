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
  • Độ giãn  = % drawdown từ đỉnh pha → đáy pha (120 phiên)
  • Chỉ dùng cho giai đoạn ĐẦU SÓNG HỒI (T7/2026)
  • Sau này → Volume + Ichimoku

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
.src-yahoo   { background:#2e1a1a; color:#e65100; }
</style>
"""

# ─────────────────────────────────────────────────────────────
#  DATA LAYER — fallback chain VCI → FireAnt → yfinance
# ─────────────────────────────────────────────────────────────

def _fetch_vnstock(symbol: str, n: int = 120):
    """Thử vnstock VCI source."""
    try:
        from vnstock import Vnstock
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=int(n * 1.7))
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        df = stock.quote.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1D",
        )
        if df is not None and len(df) >= 20:
            df.columns = [c.lower() for c in df.columns]
            return df.tail(n).reset_index(drop=True), "VCI"
    except Exception:
        pass
    return None, None


def _fetch_fireant(symbol: str, n: int = 120):
    """Thử FireAnt undocumented API."""
    try:
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=int(n * 1.7))
        url = (
            f"https://api.fireant.vn/symbols/{symbol}/historical-quotes"
            f"?startDate={start.strftime('%Y-%m-%d')}"
            f"&endDate={end.strftime('%Y-%m-%d')}"
            f"&offset=0&limit={n + 20}"
        )
        r = requests.get(url, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, None
        raw = r.json()
        if not raw:
            return None, None
        df = pd.DataFrame(raw)
        # FireAnt trả về: date, open, high, low, close, volume, dealVolume, priceAverage
        rename = {}
        for col in df.columns:
            lc = col.lower()
            if lc == "date":             rename[col] = "time"
            elif lc == "open":           rename[col] = "open"
            elif lc == "high":           rename[col] = "high"
            elif lc == "low":            rename[col] = "low"
            elif lc == "close":          rename[col] = "close"
            elif lc in ("volume", "totalvolume"): rename[col] = "volume"
        df.rename(columns=rename, inplace=True)
        df["close"] = pd.to_numeric(df.get("close", 0), errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df = df.dropna(subset=["close"])
        df = df.sort_values("time").reset_index(drop=True)
        if len(df) >= 20:
            return df.tail(n).reset_index(drop=True), "FireAnt"
    except Exception:
        pass
    return None, None


def _fetch_yfinance(symbol: str, n: int = 120):
    """Thử yfinance với suffix .VN."""
    try:
        import yfinance as yf
        ticker = f"{symbol}.VN"
        df = yf.Ticker(ticker).history(period="8mo")
        if df is None or df.empty:
            return None, None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        # yfinance trả về: date, open, high, low, close, volume
        for col in df.columns:
            if "date" in col.lower():
                df.rename(columns={col: "time"}, inplace=True)
                break
        df["close"]  = pd.to_numeric(df.get("close", 0),  errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).tail(n).reset_index(drop=True)
        if len(df) >= 20:
            return df, "Yahoo"
    except Exception:
        pass
    return None, None


def fetch_ohlcv(symbol: str, n: int = 120):
    """
    Fallback chain: VCI → FireAnt → yfinance
    Returns (df, source_name) hoặc (None, None)
    """
    df, src = _fetch_vnstock(symbol, n)
    if df is not None:
        return df, src
    df, src = _fetch_fireant(symbol, n)
    if df is not None:
        return df, src
    df, src = _fetch_yfinance(symbol, n)
    return df, src


def fetch_company_name(symbol: str) -> str:
    """Lấy tên công ty từ FireAnt (nhanh, không cần auth)."""
    try:
        url = f"https://api.fireant.vn/symbols/{symbol}"
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            d = r.json()
            return d.get("companyName", "") or d.get("name", "")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────
#  TÍNH CHỈ SỐ
# ─────────────────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame) -> dict:
    """
    Tính Sức bật, Độ giãn, Fibonacci, Swing KC/HT từ OHLCV DataFrame.

    Columns cần: close, high, low, volume (optional)
    """
    close  = df["close"].values.astype(float)
    high   = df["high"].values.astype(float)  if "high"   in df.columns else close.copy()
    low    = df["low"].values.astype(float)   if "low"    in df.columns else close.copy()
    volume = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(close))

    n          = len(close)
    price_now  = float(close[-1])
    pct_change = float((close[-1] - close[-2]) / close[-2] * 100) if n >= 2 else 0.0

    # ── Xác định pha giảm: đỉnh → đáy trong 120 phiên ──────
    peak_idx   = int(np.argmax(high))
    # tìm đáy SAU đỉnh
    sub_low    = low[peak_idx:]
    trough_sub = int(np.argmin(sub_low))
    trough_idx = peak_idx + trough_sub
    phase_high = float(high[peak_idx])
    phase_low  = float(low[trough_idx])

    drop_sessions = max(trough_idx - peak_idx, 1)
    do_gian_pct   = (phase_low - phase_high) / phase_high * 100          # âm
    do_gian_abs   = abs(do_gian_pct)
    suc_bat       = round(do_gian_abs / drop_sessions * 10, 2)           # công thức chính
    recovery_pct  = (price_now - phase_low) / phase_low * 100 if phase_low > 0 else 0.0

    # ── Fibonacci retracement (đỉnh pha → đáy pha) ─────────
    diff = phase_high - phase_low
    fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    fib_levels = []
    for r in fib_ratios:
        price_fib = phase_low + diff * r
        role = "KC" if price_fib > price_now else "HT"
        fib_levels.append({
            "price": round(price_fib, 2),
            "label": f"{r*100:.1f}%",
            "role":  role,
        })

    # ── Swing high/low cục bộ (lookback=3) ─────────────────
    swing_h, swing_l = [], []
    lb = 3
    for i in range(lb, n - lb):
        if high[i] == max(high[i-lb:i+lb+1]):
            swing_h.append(float(high[i]))
        if low[i]  == min(low[i-lb:i+lb+1]):
            swing_l.append(float(low[i]))

    # Lọc: kháng cự > giá hiện tại, hỗ trợ < giá hiện tại
    res_sw = sorted(set(round(v, 2) for v in swing_h if v > price_now))[:4]
    sup_sw = sorted(set(round(v, 2) for v in swing_l if v < price_now), reverse=True)[:4]

    return {
        "price":        round(price_now, 2),
        "pct_change":   round(pct_change, 2),
        "phase_high":   round(phase_high, 2),
        "phase_low":    round(phase_low, 2),
        "drop_sessions": drop_sessions,
        "do_gian_pct":  round(do_gian_pct, 1),
        "do_gian_abs":  round(do_gian_abs, 1),
        "suc_bat":      suc_bat,
        "recovery_pct": round(recovery_pct, 1),
        "fib_levels":   fib_levels,
        "swing_res":    res_sw,
        "swing_sup":    sup_sw,
    }


# ─────────────────────────────────────────────────────────────
#  LOOKUP UI — tra cứu 1 mã
# ─────────────────────────────────────────────────────────────

_SRC_BADGE = {
    "VCI":     '<span class="src-badge src-vci">vnstock VCI</span>',
    "FireAnt": '<span class="src-badge src-fireant">FireAnt</span>',
    "Yahoo":   '<span class="src-badge src-yahoo">Yahoo .VN</span>',
}


def _val_class(val: float, good: float, warn: float, invert: bool = False) -> str:
    """Trả về class màu dựa trên ngưỡng."""
    if invert:
        return "val-down" if val >= good else ("val-warn" if val >= warn else "val-up")
    return "val-up" if val >= good else ("val-warn" if val >= warn else "val-down")


def _render_lookup_card(symbol: str, company: str, m: dict, source: str):
    pct  = m["pct_change"]
    pc   = "val-up" if pct >= 0 else "val-down"
    ps   = "+" if pct >= 0 else ""
    dg_c = _val_class(m["do_gian_abs"], 30, 20, invert=True)   # sâu hơn = tốt hơn cho sức bật
    sb_c = _val_class(m["suc_bat"],     2.0, 1.0)

    src_html = _SRC_BADGE.get(source, f'<span class="src-badge">{source}</span>')

    # header
    st.markdown(f"""
    <div class="lk-card">
      <div class="lk-ticker">{symbol} {src_html}</div>
      <div class="lk-company">{company or "—"} · 120 phiên</div>
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

    # Fibonacci
    fib = m["fib_levels"]
    fib_rows = "".join(
        f"""<tr>
          <td><b>{f['price']:,.1f}</b></td>
          <td><span class="{'badge-r' if f['role']=='KC' else 'badge-s'}">
              {'Kháng cự' if f['role']=='KC' else 'Hỗ trợ'}</span></td>
          <td><span class="badge-fib">{f['label']} Fib</span></td>
        </tr>"""
        for f in fib
    )
    st.markdown(f"""
      <div class="lk-section">📐 Fibonacci retracement (đỉnh pha → đáy pha)</div>
      <table class="sr-table">
        <thead><tr><th>Giá</th><th>Loại</th><th>Mức Fib</th></tr></thead>
        <tbody>{fib_rows}</tbody>
      </table>
    """, unsafe_allow_html=True)

    # Swing KC/HT
    sw_res = m["swing_res"]
    sw_sup = m["swing_sup"]
    max_r  = max(len(sw_res), len(sw_sup), 1)
    sw_rows = ""
    for i in range(min(max_r, 4)):
        r_cell = f'<span class="badge-r">{sw_res[i]:,.1f}</span>' if i < len(sw_res) else "—"
        s_cell = f'<span class="badge-s">{sw_sup[i]:,.1f}</span>' if i < len(sw_sup) else "—"
        sw_rows += f"<tr><td>{r_cell}</td><td>{s_cell}</td></tr>"

    st.markdown(f"""
      <div class="lk-section">📊 Swing KC/HT cục bộ (lookback 3 phiên)</div>
      <table class="sr-table">
        <thead><tr><th>🔴 Kháng cự</th><th>🟢 Hỗ trợ</th></tr></thead>
        <tbody>{sw_rows}</tbody>
      </table>

      <div class="formula-note">
        <b>Công thức Sức bật</b> = (Độ giãn % ÷ Số phiên giảm) × 10<br>
        Giảm <b>30% trong 15 phiên</b> → Sức bật = <b>20</b> ·
        Giảm <b>30% trong 60 phiên</b> → Sức bật = <b>5</b><br>
        VIX, GEX, VRE (giảm sâu + nhanh) bật mạnh hơn CTG, TCB trong cùng pha hồi.<br>
        ⚠️ Chỉ áp dụng <b>giai đoạn đầu sóng hồi</b> (T7/2026). Sau → Volume + Ichimoku.
      </div>
    </div>
    """, unsafe_allow_html=True)


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
        with st.spinner(f"Đang lấy dữ liệu {symbol_input}…"):
            df, src = fetch_ohlcv(symbol_input, n=120)
        if df is None or len(df) < 20:
            st.error(f"❌ Không lấy được dữ liệu cho **{symbol_input}**. "
                     "Kiểm tra lại mã hoặc thử lại sau.")
            st.session_state.pop("sb_lookup_result", None)
            return
        company = fetch_company_name(symbol_input)
        metrics = compute_metrics(df)
        st.session_state["sb_lookup_result"] = {
            "symbol":  symbol_input,
            "company": company,
            "metrics": metrics,
            "source":  src,
        }

    result = st.session_state.get("sb_lookup_result")
    if result:
        _render_lookup_card(
            result["symbol"],
            result["company"],
            result["metrics"],
            result["source"],
        )

    st.divider()


# ─────────────────────────────────────────────────────────────
#  SCAN TOÀN THỊ TRƯỜNG — giữ nguyên logic cũ, bổ sung fallback
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_symbols(exchanges: list) -> list:
    symbols = []
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol="VNM", source="VCI")
        for ex in exchanges:
            try:
                df = stock.listing.symbols_by_exchange(exchange=ex)
                if df is not None and not df.empty:
                    col = "symbol" if "symbol" in df.columns else df.columns[0]
                    symbols += df[col].str.upper().tolist()
            except Exception:
                pass
    except Exception as e:
        st.warning(f"Không lấy được danh sách mã: {e}")
    return list(set(symbols))


def _compute_symbol_scan(symbol: str, n_periods: int = 120) -> dict | None:
    """Tính chỉ số cho 1 mã trong batch scan, dùng fallback chain."""
    df, src = fetch_ohlcv(symbol, n=n_periods)
    if df is None or len(df) < 20:
        return None
    try:
        m = compute_metrics(df)
        close  = df["close"].values.astype(float)
        volume = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(close))

        # Volume Profile top 4 bucket → KC/HT
        price_min, price_max = close.min(), close.max()
        if price_max == price_min:
            return None
        buckets = 20
        edges      = np.linspace(price_min, price_max, buckets + 1)
        bucket_vol = np.zeros(buckets)
        for p, v in zip(close, volume):
            idx = min(int((p - price_min) / (price_max - price_min) * buckets), buckets - 1)
            bucket_vol[idx] += v
        total_vol = bucket_vol.sum() or 1
        top4 = np.argsort(bucket_vol)[-4:][::-1]
        sr_levels = []
        for bi in top4:
            center = (edges[bi] + edges[bi + 1]) / 2
            vpct   = bucket_vol[bi] / total_vol * 100
            role   = "KC" if center > m["price"] else "HT"
            sr_levels.append((round(center, 2), round(vpct, 1), role))
        sr_levels.sort(key=lambda x: x[0])

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
def _vnindex_drawdown(n_periods: int = 120) -> float:
    df, _ = fetch_ohlcv("VNINDEX", n=n_periods)
    if df is None or df.empty:
        return 0.01
    close = df["close"].values.astype(float)
    peak  = close.max()
    now   = close[-1]
    dd    = abs((now - peak) / peak)
    return dd if dd > 0 else 0.01


def scan_all(
    symbols: list,
    n_periods: int = 120,
    batch_delay: float = 0.12,
    progress_bar=None,
    status_text=None,
) -> pd.DataFrame:
    vn_dd   = _vnindex_drawdown(n_periods)
    results = []
    total   = len(symbols)

    for i, sym in enumerate(symbols):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Đang quét {sym}… ({i+1}/{total})")
        if status_text:
            status_text.text(f"⏳ {sym}")

        row = _compute_symbol_scan(sym, n_periods)
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

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        exchanges = st.multiselect(
            "Sàn giao dịch", ["HOSE", "HNX", "UPCOM"], default=["HOSE"])
    with col2:
        n_periods = st.selectbox("Số phiên", [60, 120, 180], index=1)
    with col3:
        top_n = st.number_input("Hiển thị Top", min_value=10, max_value=200, value=50, step=10)
    with col4:
        min_dd = st.number_input("DD tối thiểu (%)", min_value=5, max_value=60, value=15)

    col_a, col_b = st.columns([1, 2])
    with col_a:
        run_btn = st.button("▶ Bắt đầu Scan", use_container_width=True,
                            type="primary", key="sb_scan_btn")
    with col_b:
        st.caption("⏱️ HOSE ~700 mã ≈ 5–10 phút | HNX+UPCOM thêm ~800 mã. Nên chọn 1 sàn trước.")

    cache_key = f"suc_bat_df_{','.join(sorted(exchanges))}_{n_periods}"

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
        df = scan_all(symbols, n_periods=n_periods, batch_delay=0.12,
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
        f"Dữ liệu: fallback chain VCI → FireAnt → Yahoo · {n_periods} phiên · "
        f"Cập nhật: {datetime.date.today().strftime('%d/%m/%Y')} · "
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
