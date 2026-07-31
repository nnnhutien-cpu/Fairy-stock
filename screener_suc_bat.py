"""
Tab "🚀 Screener Sức Bật" — Fairy-stock
========================================
Lọc toàn bộ HOSE / HNX / UPCOM theo:
  • Drawdown 120 phiên     (sức bật tiềm năng)
  • Tốc độ giảm            (độ giãn — lò xo bị nén nhanh)
  • Beta drawdown vs VNINDEX (giảm mạnh hơn thị trường)
  • Hồi phục gần đây       (đang bắt đầu bật chưa)
  • Vùng kháng cự / hỗ trợ (vùng giá quá khứ bị bán nhiều — Volume Profile đơn giản)

Tích hợp vào main.py:
    from screener_suc_bat import render_suc_bat_tab
    with tab_suc_bat:
        render_suc_bat_tab()
"""

import streamlit as st
import pandas as pd
import numpy as np
from vnstock import Vnstock
import datetime
import time

# ─────────────────────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────────────────────
_CSS = """
<style>
.sb-header {
    display: flex; align-items: center; gap: 14px;
    background: linear-gradient(135deg,#1a1a2e,#16213e);
    border-radius: 12px; padding: 16px 20px; margin-bottom: 18px;
}
.sb-title { font-size: 22px; font-weight: 800; color: #e0e0ff; }
.sb-sub   { font-size: 12px; color: #888; margin-top: 2px; }

.sb-score-badge {
    display: inline-block;
    padding: 3px 10px; border-radius: 20px;
    font-size: 13px; font-weight: 700;
}
.score-high   { background:#1a3a1a; color:#00e676; }
.score-mid    { background:#3a3a1a; color:#ffd740; }
.score-low    { background:#3a1a1a; color:#ff5252; }

.sb-stat-row {
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;
}
.sb-stat {
    background: #1e1e2e; border-radius: 10px;
    padding: 10px 16px; flex: 1; min-width: 130px;
}
.sb-stat-label { font-size: 11px; color: #888; text-transform: uppercase; }
.sb-stat-value { font-size: 20px; font-weight: 800; color: #e0e0ff; margin-top: 2px; }

.sb-note {
    background: #1a1a2e; border-left: 3px solid #8b7fb5;
    padding: 10px 14px; border-radius: 0 8px 8px 0;
    font-size: 12px; color: #aaa; margin-bottom: 14px;
}
</style>
"""

# ─────────────────────────────────────────────────────────────
#  Lấy danh sách mã
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_symbols(exchanges: list[str]) -> list[str]:
    """Lấy toàn bộ mã theo sàn từ vnstock."""
    symbols = []
    try:
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


# ─────────────────────────────────────────────────────────────
#  Tính chỉ số cho 1 mã
# ─────────────────────────────────────────────────────────────

def _compute_symbol(symbol: str, n_periods: int = 120) -> dict | None:
    """
    Trả về dict chỉ số hoặc None nếu lỗi / thiếu dữ liệu.

    Chỉ số tính:
      drawdown        : (giá hiện tại - đỉnh N phiên) / đỉnh N phiên  [âm = giảm sâu]
      speed           : drawdown / số phiên từ đỉnh đến đáy           [âm / phiên]
      beta_dd         : drawdown_mã / drawdown_VNINDEX cùng kỳ        [>1 = giảm mạnh hơn TT]
      recovery        : (giá hiện tại - đáy) / đáy                    [dương = đang bật]
      suc_bat_score   : |drawdown| * beta_dd  →  rank cao = tiềm năng bật mạnh
      do_gian_score   : |speed| * beta_dd     →  rank cao = bật nhanh hơn TT
      sr_levels       : list[(price, vol_pct)] — vùng KC/HT từ volume profile
    """
    try:
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=int(n_periods * 1.6))  # buffer weekends

        df = stock.quote.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1D",
        )
        if df is None or len(df) < 20:
            return None

        df = df.tail(n_periods).copy()
        close = df["close"].values
        volume = df["volume"].values if "volume" in df.columns else np.ones(len(close))

        price_now  = float(close[-1])
        peak_price = float(close.max())
        trough_idx = int(np.argmin(close))
        trough_val = float(close[trough_idx])
        peak_idx   = int(np.argmax(close[:trough_idx + 1])) if trough_idx > 0 else 0

        drawdown = (price_now - peak_price) / peak_price  # âm
        n_days_to_trough = max(trough_idx - peak_idx, 1)
        speed    = drawdown / n_days_to_trough            # âm / phiên
        recovery = (price_now - trough_val) / trough_val if trough_val > 0 else 0.0

        # Volume Profile — chia giá thành 20 bucket, tổng volume theo bucket
        price_min, price_max = close.min(), close.max()
        if price_max == price_min:
            return None
        buckets = 20
        edges   = np.linspace(price_min, price_max, buckets + 1)
        bucket_vol = np.zeros(buckets)
        for i, (p, v) in enumerate(zip(close, volume)):
            idx = min(int((p - price_min) / (price_max - price_min) * buckets), buckets - 1)
            bucket_vol[idx] += v
        total_vol = bucket_vol.sum() or 1
        # Lấy top 4 bucket volume cao nhất → vùng kháng cự/hỗ trợ
        top4 = np.argsort(bucket_vol)[-4:][::-1]
        sr_levels = []
        for bi in top4:
            center = (edges[bi] + edges[bi + 1]) / 2
            vpct   = bucket_vol[bi] / total_vol * 100
            role   = "KC" if center > price_now else "HT"
            sr_levels.append((round(center, 2), round(vpct, 1), role))
        sr_levels.sort(key=lambda x: x[0])

        return {
            "symbol":       symbol,
            "price":        round(price_now, 2),
            "drawdown_pct": round(drawdown * 100, 2),
            "speed_pday":   round(speed * 100, 4),
            "recovery_pct": round(recovery * 100, 2),
            "peak_price":   round(peak_price, 2),
            "trough_price": round(trough_val, 2),
            "sr_levels":    sr_levels,
            # scores tính sau khi có beta
            "_drawdown_abs": abs(drawdown),
            "_speed_abs":    abs(speed),
        }
    except Exception:
        return None


@st.cache_data(ttl=1800)
def _vnindex_drawdown(n_periods: int = 120) -> float:
    """Drawdown VNINDEX cùng kỳ — dùng để tính beta."""
    try:
        stock = Vnstock().stock(symbol="VNINDEX", source="VCI")
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=int(n_periods * 1.6))
        df = stock.quote.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1D",
        )
        if df is None or df.empty:
            return 1.0
        close = df["close"].tail(n_periods).values
        peak  = close.max()
        now   = close[-1]
        dd    = abs((now - peak) / peak)
        return dd if dd > 0 else 0.01
    except Exception:
        return 0.01


# ─────────────────────────────────────────────────────────────
#  Batch scan với progress
# ─────────────────────────────────────────────────────────────

def scan_all(
    symbols: list[str],
    n_periods: int = 120,
    batch_delay: float = 0.15,
    progress_bar=None,
    status_text=None,
) -> pd.DataFrame:
    """
    Quét toàn bộ symbols, trả về DataFrame đã tính score.
    batch_delay: giây nghỉ giữa mỗi mã (tránh rate limit vnstock).
    """
    vn_dd = _vnindex_drawdown(n_periods)
    results = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Đang quét {sym}… ({i+1}/{total})")
        if status_text:
            status_text.text(f"⏳ {sym}")

        row = _compute_symbol(sym, n_periods)
        if row:
            # Beta drawdown
            beta = row["_drawdown_abs"] / vn_dd if vn_dd > 0 else 1.0
            row["beta_dd"]       = round(beta, 2)
            row["suc_bat_score"] = round(row["_drawdown_abs"] * beta * 100, 2)
            row["do_gian_score"] = round(row["_speed_abs"]    * beta * 1000, 2)
            results.append(row)

        time.sleep(batch_delay)

    df = pd.DataFrame(results)
    if df.empty:
        return df

    # Rank percentile (0–100) để normalize hiển thị
    for col in ["suc_bat_score", "do_gian_score", "recovery_pct"]:
        if col in df.columns:
            df[f"{col}_rank"] = df[col].rank(pct=True).mul(100).round(1)

    # Composite score: 50% sức bật + 30% độ giãn + 20% recovery
    df["tong_score"] = (
        df.get("suc_bat_score_rank", 0) * 0.5 +
        df.get("do_gian_score_rank", 0) * 0.3 +
        df.get("recovery_pct_rank",  0) * 0.2
    ).round(1)

    df.sort_values("tong_score", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ─────────────────────────────────────────────────────────────
#  Hiển thị kết quả
# ─────────────────────────────────────────────────────────────

def _score_badge(score: float) -> str:
    if score >= 70:
        return f'<span class="sb-score-badge score-high">⚡ {score:.0f}</span>'
    elif score >= 40:
        return f'<span class="sb-score-badge score-mid">🔥 {score:.0f}</span>'
    else:
        return f'<span class="sb-score-badge score-low">❄️ {score:.0f}</span>'


def _sr_str(sr_levels: list) -> str:
    """Tóm tắt KC/HT thành chuỗi ngắn."""
    kc = [f"{p}" for p, v, r in sr_levels if r == "KC"]
    ht = [f"{p}" for p, v, r in sr_levels if r == "HT"]
    parts = []
    if kc:
        parts.append("KC: " + " / ".join(kc[:2]))
    if ht:
        parts.append("HT: " + " / ".join(ht[:2]))
    return " | ".join(parts) if parts else "—"


# ─────────────────────────────────────────────────────────────
#  Render chính
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
        ⚠️ Screener này áp dụng cho <b>giai đoạn đầu sóng hồi</b> (hiện tại T7/2026).
        Về sau cần kết hợp Volume + Ichimoku — không áp dụng mãi.
    </div>
    """, unsafe_allow_html=True)

    # ── Cấu hình ──────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        exchanges = st.multiselect(
            "Sàn giao dịch",
            ["HOSE", "HNX", "UPCOM"],
            default=["HOSE"],
        )
    with col2:
        n_periods = st.selectbox("Số phiên", [60, 120, 180], index=1)
    with col3:
        top_n = st.number_input("Hiển thị Top", min_value=10, max_value=200, value=50, step=10)
    with col4:
        min_dd = st.number_input("DD tối thiểu (%)", min_value=5, max_value=60, value=15)

    col_a, col_b = st.columns([1, 2])
    with col_a:
        run_btn = st.button("▶ Bắt đầu Scan", use_container_width=True, type="primary")
    with col_b:
        st.caption("⏱️ HOSE ~700 mã ≈ 5–10 phút | HNX+UPCOM thêm ~800 mã. Nên chọn 1 sàn trước.")

    # ── Cache key ─────────────────────────────
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
        prog  = st.progress(0)
        status = st.empty()

        df = scan_all(
            symbols,
            n_periods=n_periods,
            batch_delay=0.12,
            progress_bar=prog,
            status_text=status,
        )
        st.session_state[cache_key] = df
        prog.empty()
        status.empty()

    df: pd.DataFrame = st.session_state.get(cache_key, pd.DataFrame())

    if df.empty:
        st.info("Nhấn **▶ Bắt đầu Scan** để quét.")
        return

    # ── Filter ────────────────────────────────
    df_show = df[df["drawdown_pct"] <= -abs(min_dd)].head(top_n).copy()

    # ── Summary stats ─────────────────────────
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
            <div class="sb-stat-label">Đang hồi TB top 10</div>
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

    # ── Bảng kết quả ──────────────────────────
    display_cols = {
        "symbol":        "Mã",
        "price":         "Giá",
        "drawdown_pct":  "DD% (6T)",
        "speed_pday":    "Tốc độ%/ngày",
        "beta_dd":       "Beta DD",
        "recovery_pct":  "Hồi%",
        "tong_score":    "⭐ Tổng Score",
    }

    df_table = df_show[list(display_cols.keys())].rename(columns=display_cols).copy()

    # Style màu
    def _style(df_s):
        styles = pd.DataFrame("", index=df_s.index, columns=df_s.columns)
        if "DD% (6T)" in df_s.columns:
            styles["DD% (6T)"] = df_s["DD% (6T)"].apply(
                lambda v: "color:#ff5252;font-weight:700" if v < -30
                else ("color:#ff8a65" if v < -20 else "color:#ffcc80")
            )
        if "Hồi%" in df_s.columns:
            styles["Hồi%"] = df_s["Hồi%"].apply(
                lambda v: "color:#00e676;font-weight:700" if v > 10
                else ("color:#69db7c" if v > 5 else "color:#aaa")
            )
        if "⭐ Tổng Score" in df_s.columns:
            styles["⭐ Tổng Score"] = df_s["⭐ Tổng Score"].apply(
                lambda v: "color:#00e676;font-weight:800" if v >= 70
                else ("color:#ffd740;font-weight:700" if v >= 40 else "color:#ff5252")
            )
        return styles

    styled = df_table.style.apply(_style, axis=None).format({
        "Giá":           "{:,.2f}",
        "DD% (6T)":      "{:.1f}%",
        "Tốc độ%/ngày":  "{:.3f}%",
        "Beta DD":       "{:.2f}x",
        "Hồi%":          "+{:.1f}%",
        "⭐ Tổng Score":  "{:.0f}",
    })

    st.dataframe(styled, use_container_width=True, hide_index=True, height=520)

    # ── Chi tiết KC/HT cho mã được chọn ───────
    st.markdown("---")
    st.markdown("#### 🎯 Vùng Kháng Cự / Hỗ Trợ (Volume Profile)")
    selected_sym = st.selectbox(
        "Chọn mã xem chi tiết KC/HT",
        options=df_show["symbol"].tolist(),
    )
    row = df_show[df_show["symbol"] == selected_sym].iloc[0]

    sr = row.get("sr_levels", [])
    if sr:
        kc_list = [(p, v) for p, v, r in sr if r == "KC"]
        ht_list = [(p, v) for p, v, r in sr if r == "HT"]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🔴 Kháng cự** (vùng bán mạnh quá khứ)")
            for p, v in kc_list:
                st.markdown(
                    f"<span style='color:#ff5252;font-weight:700'>{p:,.2f}</span>"
                    f" &nbsp; vol tập trung: <span style='color:#aaa'>{v:.1f}%</span>",
                    unsafe_allow_html=True,
                )
        with c2:
            st.markdown("**🟢 Hỗ trợ** (vùng mua mạnh quá khứ)")
            for p, v in ht_list:
                st.markdown(
                    f"<span style='color:#00e676;font-weight:700'>{p:,.2f}</span>"
                    f" &nbsp; vol tập trung: <span style='color:#aaa'>{v:.1f}%</span>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Không có dữ liệu KC/HT cho mã này.")

    # ── Export ────────────────────────────────
    st.markdown("---")
    csv = df_show.drop(columns=["sr_levels", "_drawdown_abs", "_speed_abs"], errors="ignore").to_csv(index=False)
    st.download_button(
        "⬇️ Tải kết quả CSV",
        data=csv,
        file_name=f"suc_bat_screener_{datetime.date.today()}.csv",
        mime="text/csv",
    )

    st.caption(
        f"Dữ liệu: vnstock VCI · {n_periods} phiên · "
        f"Cập nhật: {datetime.date.today().strftime('%d/%m/%Y')} · "
        "Không phải khuyến nghị đầu tư"
    )
