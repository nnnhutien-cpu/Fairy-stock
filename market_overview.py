"""
market_overview.py - Cụm "Phân tích xu hướng" của tab Thị Trường.

Nguyên tắc chống "chỗ có chỗ không":
  1. Mỗi chỉ báo chỉ hiện số khi ĐỦ dữ liệu để tính (MA200 cần >=200 phiên, MACD >=35, RSI >=15...).
     Thiếu -> hiện "—" kèm LÝ DO cụ thể. Không bao giờ điền giá trị mặc định giả (RSI 50, MACD 0).
  2. Khuyến nghị chỉ tính trên các thành phần ĐANG CÓ và hiển thị độ phủ (vd 3/5). Dưới 3/5 -> từ chối đưa ra kết luận.
  3. Mọi thẻ đều ghi "đến phiên dd/mm" và cảnh báo khi dữ liệu cũ.

Dùng:
    from market_overview import render_market_overview
    df = get_vnindex_data()                       # DataFrame: time, open, high, low, close, volume
    render_market_overview(df, breadth=get_market_breadth(), pe={"current": 11.9, "mean": 16.4, "percentile": 20})
"""
from __future__ import annotations

import math

import pandas as pd
import streamlit as st

MIN_COVERAGE = 3  # cần tối thiểu 3/5 thành phần mới đưa ra khuyến nghị


# ---------------------------------------------------------------- tính toán
def _ok(x):
    try:
        return x is not None and not math.isnan(float(x)) and not math.isinf(float(x))
    except (TypeError, ValueError):
        return False


def compute_index_snapshot(df: pd.DataFrame) -> dict:
    """Tính MA/RSI/MACD/Volume từ nến ngày. Trường nào thiếu dữ liệu -> None + giải thích trong notes."""
    s = {"as_of": None, "n_rows": 0, "close": None, "chg": None, "chg_pct": None,
         "ma": {20: None, 50: None, 200: None}, "rsi": None, "macd": None, "signal": None, "hist": None,
         "vol": None, "vol_avg20": None, "vol_ratio": None, "notes": {}}
    if df is None or len(df) == 0 or "close" not in df.columns:
        s["notes"]["all"] = "Chưa lấy được dữ liệu VN-INDEX từ bất kỳ nguồn nào"
        return s

    d = df.copy()
    if "time" in d.columns:
        d["time"] = pd.to_datetime(d["time"], errors="coerce")
        d = d.dropna(subset=["time"]).sort_values("time")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"])
    d = d[d["close"] > 0].reset_index(drop=True)
    n = len(d)
    s["n_rows"] = n
    if n == 0:
        s["notes"]["all"] = "Dữ liệu VN-INDEX rỗng sau khi làm sạch"
        return s

    close = d["close"]
    s["close"] = float(close.iloc[-1])
    if "time" in d.columns:
        s["as_of"] = d["time"].iloc[-1].date()
    if n >= 2:
        s["chg"] = float(close.iloc[-1] - close.iloc[-2])
        s["chg_pct"] = s["chg"] / float(close.iloc[-2]) * 100

    for w in (20, 50, 200):
        if n >= w:
            s["ma"][w] = float(close.rolling(w).mean().iloc[-1])
        else:
            s["notes"][f"ma{w}"] = f"cần ≥{w} phiên, hiện có {n}"

    if n >= 15:
        delta = close.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        last_up, last_dn = up.iloc[-1], dn.iloc[-1]
        if _ok(last_up) and _ok(last_dn):
            s["rsi"] = 100.0 if last_dn == 0 else float(100 - 100 / (1 + last_up / last_dn))
    else:
        s["notes"]["rsi"] = f"cần ≥15 phiên, hiện có {n}"

    if n >= 35:
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        sig = macd.ewm(span=9, adjust=False).mean()
        s["macd"], s["signal"], s["hist"] = float(macd.iloc[-1]), float(sig.iloc[-1]), float(macd.iloc[-1] - sig.iloc[-1])
    else:
        s["notes"]["macd"] = f"cần ≥35 phiên, hiện có {n}"

    if "volume" in d.columns:
        v = pd.to_numeric(d["volume"], errors="coerce").fillna(0)
        recent = v.tail(20)
        if n >= 20 and (recent > 0).sum() >= 10:
            s["vol"] = float(v.iloc[-1])
            s["vol_avg20"] = float(recent.mean())
            if s["vol_avg20"] > 0 and s["vol"] > 0:
                s["vol_ratio"] = s["vol"] / s["vol_avg20"]
            else:
                s["notes"]["vol"] = "khối lượng phiên gần nhất bằng 0 (nguồn chưa cập nhật)"
        else:
            s["notes"]["vol"] = "nguồn không cung cấp khối lượng chỉ số (≥10/20 phiên gần nhất bằng 0)"
    else:
        s["notes"]["vol"] = "nguồn không có cột khối lượng"
    return s


def recommend(snap: dict, breadth: dict | None = None, breadth_usable: bool = True, pe: dict | None = None) -> dict:
    """Điểm tổng hợp từ tối đa 5 thành phần (mỗi thành phần -1/0/+1). Chỉ tính thành phần có dữ liệu."""
    parts = []  # (tên, điểm hoặc None, giải thích)
    c, ma = snap.get("close"), snap.get("ma", {})

    if _ok(c) and _ok(ma.get(20)) and _ok(ma.get(50)):
        v = 1 if (c > ma[50] and ma[20] > ma[50]) else (-1 if (c < ma[50] and ma[20] < ma[50]) else 0)
        parts.append(("Xu hướng trung hạn (giá vs MA20/MA50)", v, {1: "giá & MA20 trên MA50", -1: "giá & MA20 dưới MA50", 0: "lẫn lộn"}[v]))
    else:
        parts.append(("Xu hướng trung hạn (giá vs MA20/MA50)", None, "thiếu MA20/MA50"))

    if _ok(c) and _ok(ma.get(200)):
        v = 1 if c > ma[200] else -1
        parts.append(("Xu hướng dài hạn (giá vs MA200)", v, "trên MA200" if v > 0 else "dưới MA200"))
    else:
        parts.append(("Xu hướng dài hạn (giá vs MA200)", None, snap["notes"].get("ma200", "thiếu MA200")))

    if _ok(snap.get("hist")) and _ok(snap.get("rsi")):
        h, r = snap["hist"], snap["rsi"]
        v = 1 if (h > 0 and r > 50) else (-1 if (h < 0 and r < 50) else 0)
        parts.append(("Động lượng (MACD + RSI)", v, f"MACD hist {h:+.2f}, RSI {r:.0f}"))
    else:
        parts.append(("Động lượng (MACD + RSI)", None, "thiếu MACD/RSI"))

    if breadth and breadth_usable:
        bs = breadth.get("breadth_score", 0)
        v = 1 if bs >= 3 else (-1 if bs <= -3 else 0)
        parts.append(("Độ rộng thị trường (breadth)", v, f"breadth score {bs:+d}"))
    else:
        parts.append(("Độ rộng thị trường (breadth)", None, "chưa có hoặc dữ liệu breadth đã cũ"))

    if pe and _ok(pe.get("percentile")):
        p = float(pe["percentile"])
        v = 1 if p <= 25 else (-1 if p >= 75 else 0)
        parts.append(("Định giá P/E (percentile 20 năm)", v, f"percentile {p:.0f}%"))
    else:
        parts.append(("Định giá P/E (percentile 20 năm)", None, "chưa có dữ liệu P/E"))

    avail = [p for p in parts if p[1] is not None]
    cov = len(avail)
    score = sum(p[1] for p in avail)
    out = {"parts": parts, "coverage": cov, "total": len(parts), "score": score, "reliable": cov >= MIN_COVERAGE}
    if not out["reliable"]:
        out.update(label="CHƯA ĐỦ DỮ LIỆU", icon="⚪", stock=None)
    else:
        for th, label, icon, stock in [(3, "TĂNG MẠNH", "🟢", 80), (1, "TĂNG NHẸ", "🟢", 65), (0, "TRUNG LẬP", "🟡", 50),
                                        (-2, "GIẢM NHẸ", "🟠", 40), (-99, "GIẢM MẠNH", "🔴", 20)]:
            if score >= th:
                out.update(label=label, icon=icon, stock=stock)
                break
    return out


# ---------------------------------------------------------------- hiển thị
def _fmt(x, f="{:,.2f}"):
    return f.format(x) if _ok(x) else "—"


def _row(label, value, hint=""):
    a, b = st.columns([1, 1.3])
    a.caption(label)
    b.markdown(f"**{value}**" + (f"  <span style='opacity:.65;font-size:.8em'>{hint}</span>" if hint else ""),
               unsafe_allow_html=True)


def _status(ok_count, total, note=""):
    if ok_count == total:
        st.caption("✅ Đủ dữ liệu")
    elif ok_count == 0:
        st.caption(f"⚪ Chưa có dữ liệu{' — ' + note if note else ''}")
    else:
        st.caption(f"🟡 Có {ok_count}/{total} chỉ báo{' — ' + note if note else ''}")


def _pos(c, ref):
    if not (_ok(c) and _ok(ref) and ref):
        return ""
    return f"{(c / ref - 1) * 100:+.1f}%"


def render_market_overview(df_index: pd.DataFrame, breadth: dict | None = None, pe: dict | None = None):
    snap = compute_index_snapshot(df_index)

    # --- độ mới của dữ liệu giá
    stale_note = ""
    if snap["as_of"] is not None:
        try:
            from market_breadth import _expected_latest_trading_date
            exp = _expected_latest_trading_date()
            if snap["as_of"] < exp:
                stale_note = f"⚠️ Giá VN-INDEX mới đến phiên {snap['as_of']:%d/%m/%Y} (kỳ vọng {exp:%d/%m/%Y})."
        except Exception:
            pass
    if "all" in snap["notes"]:
        st.error(f"🚨 {snap['notes']['all']}. Các thẻ giá/kỹ thuật bên dưới sẽ để trống thay vì hiển thị số giả. "
                 "Bấm **CẬP NHẬT DỮ LIỆU** hoặc kiểm tra mục *Sức khoẻ dữ liệu* ở sidebar.")
    elif stale_note:
        st.warning(stale_note)

    head = f"VN-INDEX {_fmt(snap['close'])} điểm" if _ok(snap["close"]) else "VN-INDEX —"
    if _ok(snap["chg"]):
        head += f" ({snap['chg']:+.2f} · {snap['chg_pct']:+.2f}%)"
    st.markdown(f"#### 🧠 Phân tích xu hướng")
    if snap["as_of"]:
        st.caption(f"{head} · đến phiên {snap['as_of']:%d/%m/%Y} · {snap['n_rows']} phiên dữ liệu")

    c1, c2, c3, c4 = st.columns(4)

    with c1.container(border=True):
        st.markdown("**📈 Xu hướng giá**")
        n_ok = sum(_ok(snap["ma"][w]) for w in (20, 50, 200))
        for w in (20, 50, 200):
            _row(f"MA{w}", _fmt(snap["ma"][w]), _pos(snap["close"], snap["ma"][w]))
        _status(n_ok, 3, "; ".join(snap["notes"][k] for k in ("ma20", "ma50", "ma200") if k in snap["notes"] and not _ok(snap["ma"][int(k[2:])]))[:70])

    with c2.container(border=True):
        st.markdown("**📊 Chỉ báo kỹ thuật**")
        r = snap["rsi"]
        _row("RSI(14)", _fmt(r, "{:.1f}"),
             "" if not _ok(r) else ("quá mua" if r >= 70 else "quá bán" if r <= 30 else "trung tính"))
        _row("MACD", _fmt(snap["macd"], "{:+.2f}"))
        _row("Signal", _fmt(snap["signal"], "{:+.2f}"))
        h = snap["hist"]
        _row("Histogram", _fmt(h, "{:+.2f}"), "" if not _ok(h) else ("tăng tốc" if h > 0 else "giảm tốc"))
        _status(sum(_ok(x) for x in (r, snap["macd"])), 2, snap["notes"].get("rsi") or snap["notes"].get("macd", ""))

    with c3.container(border=True):
        st.markdown("**🔊 Dòng tiền (khối lượng)**")
        _row("KL phiên gần nhất", _fmt(snap["vol"], "{:,.0f}"))
        _row("TB 20 phiên", _fmt(snap["vol_avg20"], "{:,.0f}"))
        vr = snap["vol_ratio"]
        _row("So với TB20", _fmt(vr, "{:.0%}"), "" if not _ok(vr) else ("đột biến" if vr >= 1.5 else "cạn kiệt" if vr <= 0.7 else "bình thường"))
        _status(1 if _ok(vr) else 0, 1, snap["notes"].get("vol", ""))

    with c4.container(border=True):
        st.markdown("**💰 Định giá P/E**")
        if pe and _ok(pe.get("current")):
            _row("P/E hiện tại", f"{pe['current']:.1f}x")
            _row("TB 20 năm", _fmt(pe.get("mean"), "{:.1f}x"),
                 "" if not (_ok(pe.get("mean")) and pe["mean"]) else f"{(pe['current'] / pe['mean'] - 1) * 100:+.1f}% vs TB")
            p = pe.get("percentile")
            _row("Percentile", _fmt(p, "{:.0f}%"), "" if not _ok(p) else ("rẻ" if p <= 25 else "đắt" if p >= 75 else "hợp lý"))
            st.caption("✅ Đủ dữ liệu")
        else:
            _row("P/E hiện tại", "—"); _row("TB 20 năm", "—"); _row("Percentile", "—")
            st.caption("⚪ Chưa có dữ liệu P/E")

    # --- khuyến nghị
    usable = True
    if breadth:
        try:
            from market_breadth import breadth_freshness
            f = breadth_freshness(breadth)
            usable = not (f["is_stale"] or f["data_stale"])
        except Exception:
            usable = True
    rec = recommend(snap, breadth, usable, pe)

    st.markdown("#### 💡 Khuyến nghị hành động")
    with st.container(border=True):
        a, b, c, d = st.columns([1.4, 1, 1, 1])
        a.markdown(f"### {rec['icon']} {rec['label']}")
        a.caption(f"Dựa trên {rec['coverage']}/{rec['total']} thành phần")
        if rec["reliable"]:
            b.metric("Điểm", f"{rec['score']:+d}")
            c.metric("Tỷ trọng cổ phiếu", f"{rec['stock']}%")
            d.metric("Tiền mặt", f"{100 - rec['stock']}%")
            st.progress(rec["stock"] / 100, text=f"Cổ phiếu {rec['stock']}% · Tiền mặt {100 - rec['stock']}%")
        else:
            st.info(f"Chỉ có {rec['coverage']}/{rec['total']} thành phần dữ liệu (cần ≥{MIN_COVERAGE}) nên hệ thống "
                    "không đưa ra tỷ trọng để tránh kết luận từ dữ liệu thiếu.")
        with st.expander("Căn cứ chi tiết"):
            for name, v, why in rec["parts"]:
                icon = "⚪" if v is None else ("🟢" if v > 0 else ("🔴" if v < 0 else "🟡"))
                st.markdown(f"{icon} **{name}** — {why}")
        st.caption("Mô hình tham khảo dựa trên quy tắc đơn giản, không phải lời khuyên đầu tư.")
