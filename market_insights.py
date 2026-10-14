"""
market_insights.py — Bộ não của tab "🌟 Thị Trường".

Không phụ thuộc streamlit -> test được độc lập bằng dữ liệu giá ngày.

Luồng phân tích (mỗi lớp trả lời 1 câu hỏi của nhà đầu tư):
  1. index_metrics()   : VN-Index đang ở đâu? (MA, động lượng, đỉnh/đáy 52 tuần, ngày phân phối, FTD)
  2. classify_regime() : Thị trường đang ở PHA nào? (tăng / điều chỉnh / hồi phục / giảm)
  3. breadth_view()    : Đà tăng/giảm có LAN TỎA không hay chỉ vài cổ phiếu trụ kéo?
  4. relative_perf()   : Dòng tiền đang vào nhóm vốn hoá lớn (VN30) hay lan sang mid/small (HNX, UPCOM)?
  5. score_market()    : Gộp tất cả thành 1 bảng điểm minh bạch -> tỷ trọng cổ phiếu gợi ý
  6. headline() / watch_levels(): 1 câu kết luận + các mốc giá cần theo dõi để đổi quyết định
"""
import math

import numpy as np
import pandas as pd


# ════════════════════════════════════════════════════════════════════
# TIỆN ÍCH
# ════════════════════════════════════════════════════════════════════
def _f(x, default=None):
    """Ép về float an toàn (None / NaN / inf -> default)."""
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _pct(a, b):
    a, b = _f(a), _f(b)
    if a is None or b in (None, 0):
        return None
    return (a / b - 1) * 100


def normalize_daily(df):
    """Đưa DataFrame giá ngày về [time, open, high, low, close, volume], tăng dần, 1 dòng/ngày."""
    if df is None or len(df) == 0:
        return None
    d = df.copy()
    if isinstance(d.index, pd.DatetimeIndex):
        d = d.reset_index()
    d.columns = [str(c).lower().strip() for c in d.columns]
    for cand in ("tradingdate", "date", "datetime", "index"):
        if "time" not in d.columns and cand in d.columns:
            d = d.rename(columns={cand: "time"})
    d = d.loc[:, ~d.columns.duplicated()]
    if "time" not in d.columns or "close" not in d.columns:
        return None
    t = pd.to_datetime(d["time"], errors="coerce")
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    d["time"] = t.dt.normalize()
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    d["open"] = d["open"].fillna(d["close"])
    d["high"] = d["high"].fillna(d["close"])
    d["low"] = d["low"].fillna(d["close"])
    d["volume"] = d["volume"].fillna(0.0)
    d = (d.dropna(subset=["time", "close"])
           .sort_values("time").drop_duplicates("time", keep="last")
           .reset_index(drop=True))
    return d[["time", "open", "high", "low", "close", "volume"]] if len(d) else None


def _rsi_wilder(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.where(loss != 0, 100.0)


# ════════════════════════════════════════════════════════════════════
# 1. CHỈ SỐ KỸ THUẬT CỦA VN-INDEX
# ════════════════════════════════════════════════════════════════════
DIST_WINDOW = 25        # O'Neil: đếm ngày phân phối trong 25 phiên
DIST_DROP_PCT = -0.2    # giảm >= 0,2% ...
FTD_MIN_GAIN = 1.2      # FTD: tăng >= 1,2% (thị trường VN biên độ hẹp hơn Mỹ nên dùng 1,2% thay 1,5-2%)


def distribution_days(d, window=DIST_WINDOW):
    """Ngày phân phối = chỉ số giảm >= 0,2% với khối lượng CAO HƠN phiên trước.
    Dấu hiệu tổ chức đang bán ra. >= 5-6 ngày trong 25 phiên thường đi trước các nhịp điều chỉnh."""
    if d is None or len(d) < window + 1:
        return 0, []
    chg = d["close"].pct_change() * 100
    is_dist = (chg <= DIST_DROP_PCT) & (d["volume"] > d["volume"].shift(1))
    tail = d.loc[is_dist].tail(len(d))
    recent = tail[tail.index >= len(d) - window]
    return int(len(recent)), [t.strftime("%d/%m") for t in recent["time"]]


def follow_through_day(d, lookback=25, max_age=15):
    """Follow-Through Day (O'Neil): sau một đáy (giảm >= 7% từ đỉnh 60 phiên trước đó),
    từ ngày thứ 4 của nhịp hồi trở đi có 1 phiên tăng mạnh (>= 1,2%) với khối lượng cao hơn phiên trước,
    và chưa thủng đáy. Là tín hiệu xác nhận đáy phổ biến. Trả về dict hoặc None."""
    if d is None or len(d) < 70:
        return None
    win = d.tail(lookback)
    low_idx = win["close"].idxmin()
    prior_peak = d.loc[max(0, low_idx - 60):low_idx, "close"].max()
    low_close = d.at[low_idx, "close"]
    if prior_peak <= 0 or (low_close / prior_peak - 1) * 100 > -7:
        return None  # không có nhịp điều chỉnh đủ sâu -> khái niệm FTD không áp dụng
    after = d.loc[low_idx + 1:]
    if after.empty or after["low"].min() < d.at[low_idx, "low"]:
        return None  # đã thủng đáy -> nhịp hồi bị huỷ
    chg = d["close"].pct_change() * 100
    for i in after.index:
        day_n = i - low_idx + 1  # ngày đáy tính là ngày 1
        if day_n >= 4 and chg.at[i] >= FTD_MIN_GAIN and d.at[i, "volume"] > d.at[i - 1, "volume"]:
            age = len(d) - 1 - i
            if age <= max_age:
                return {"date": d.at[i, "time"], "gain": float(chg.at[i]), "age": int(age),
                        "low_date": d.at[low_idx, "time"], "low": float(low_close),
                        "drawdown": float((low_close / prior_peak - 1) * 100)}
            return None
    return None


def index_metrics(df):
    """Tất cả chỉ số cần cho tab Thị Trường, tính từ giá NGÀY của VN-Index."""
    d = normalize_daily(df)
    if d is None or len(d) < 30:
        return None
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]

    ma20, ma50, ma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    rsi = _rsi_wilder(c)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    sig = macd.ewm(span=9, adjust=False).mean()
    hist = macd - sig
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    vol_ma20 = v.rolling(20).mean()

    price = float(c.iloc[-1])
    last52 = d.tail(250)
    hi52_i, lo52_i = last52["high"].idxmax(), last52["low"].idxmin()
    n_dist, dist_dates = distribution_days(d)

    def back(s, n):
        return _f(s.iloc[-1 - n]) if len(s) > n else None

    m = {
        "date": d["time"].iloc[-1],
        "price": price,
        "chg_pct": _pct(price, c.iloc[-2]) if len(c) >= 2 else None,
        "ma20": _f(ma20.iloc[-1]), "ma50": _f(ma50.iloc[-1]), "ma200": _f(ma200.iloc[-1]),
        # độ dốc: so với 10 phiên (MA50) và 20 phiên (MA200) trước
        "ma50_slope": _pct(ma50.iloc[-1], back(ma50, 10)),
        "ma200_slope": _pct(ma200.iloc[-1], back(ma200, 20)),
        "rsi": _f(rsi.iloc[-1]),
        "macd": _f(macd.iloc[-1]), "macd_signal": _f(sig.iloc[-1]),
        "macd_hist": _f(hist.iloc[-1]), "macd_hist_prev": back(hist, 1),
        "roc5": _pct(price, back(c, 5)), "roc20": _pct(price, back(c, 20)), "roc60": _pct(price, back(c, 60)),
        "high52": float(last52.at[hi52_i, "high"]), "high52_date": last52.at[hi52_i, "time"],
        "low52": float(last52.at[lo52_i, "low"]), "low52_date": last52.at[lo52_i, "time"],
        "dd_from_high": _pct(price, last52["high"].max()),
        "up_from_low": _pct(price, last52["low"].min()),
        "support20": float(l.tail(20).min()), "resist20": float(h.tail(20).max()),
        "support60": float(l.tail(60).min()),
        "atr_pct": _f(atr.iloc[-1] / price * 100),
        "vol": _f(v.iloc[-1]), "vol_ma20": _f(vol_ma20.iloc[-1]),
        "vol_ratio": (_f(v.iloc[-1]) / _f(vol_ma20.iloc[-1])) if _f(vol_ma20.iloc[-1]) else None,
        "dist_days": n_dist, "dist_dates": dist_dates,
        "ftd": follow_through_day(d),
        "n_sessions": len(d),
    }
    # khung dữ liệu cho biểu đồ (1 năm gần nhất)
    chart = d.tail(250).copy()
    chart["ma20"], chart["ma50"], chart["ma200"] = ma20.tail(250), ma50.tail(250), ma200.tail(250)
    m["_chart"] = chart
    return m


# ════════════════════════════════════════════════════════════════════
# 2. PHA THỊ TRƯỜNG
# ════════════════════════════════════════════════════════════════════
REGIMES = {
    "uptrend":    ("📈 XU HƯỚNG TĂNG",              "success",
                   "Giá trên MA50 và MA200, MA50 nằm trên MA200: xu hướng chính đang tăng."),
    "pullback":   ("↘️ ĐIỀU CHỈNH TRONG XU HƯỚNG TĂNG", "warning",
                   "Giá đã rơi xuống dưới MA50 nhưng vẫn trên MA200: xu hướng dài hạn chưa gãy, đang điều chỉnh."),
    "recovery":   ("↗️ HỒI PHỤC – CHƯA XÁC NHẬN",   "info",
                   "Giá đã vượt MA50 nhưng còn dưới MA200 (hoặc MA50 < MA200): nhịp hồi, cần thêm xác nhận."),
    "downtrend":  ("📉 XU HƯỚNG GIẢM",              "danger",
                   "Giá dưới cả MA50 và MA200: xu hướng chính đang giảm, ưu tiên bảo toàn vốn."),
    "unknown":    ("❔ CHƯA XÁC ĐỊNH",               "gray",
                   "Chưa đủ dữ liệu (cần ≥ 200 phiên) để xác định pha thị trường."),
}


def classify_regime(m):
    if not m or m.get("ma50") is None:
        return "unknown"
    p, ma50, ma200 = m["price"], m["ma50"], m.get("ma200")
    if ma200 is None:  # chưa đủ 200 phiên -> chỉ dựa vào MA50
        return "uptrend" if p > ma50 and (m.get("ma50_slope") or 0) > 0 else ("downtrend" if p < ma50 else "recovery")
    if p > ma200:
        return "uptrend" if (p > ma50 and ma50 > ma200) else ("pullback" if p < ma50 else "recovery")
    return "recovery" if p > ma50 else "downtrend"


# ════════════════════════════════════════════════════════════════════
# 3. ĐỘ RỘNG THỊ TRƯỜNG
# ════════════════════════════════════════════════════════════════════
def breadth_view(breadth, m=None, max_lag_days=4):
    """Đọc breadth.json (bot nền) + phát hiện PHÂN KỲ giữa chỉ số và độ rộng."""
    if not breadth:
        return None
    hist = pd.DataFrame(breadth.get("history") or [])
    if not hist.empty and {"d", "a", "dc"} <= set(hist.columns):
        hist = hist.rename(columns={"d": "date", "a": "adv", "dc": "dec"})
        hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
        hist = hist.dropna(subset=["date"])
        hist = hist[(hist["adv"] + hist["dec"]) > 0].sort_values("date").reset_index(drop=True)
        hist["net"] = hist["adv"] - hist["dec"]
        hist["ad_line"] = hist["net"].cumsum()
    else:
        hist = pd.DataFrame()

    out = {
        "pct50": _f(breadth.get("pct_above_ma50")),
        "pct20": _f(breadth.get("pct_above_ma20")),
        "pct100": _f(breadth.get("pct_above_ma100")),
        "ad_pct": _f(breadth.get("ad_pct")),
        "advance": breadth.get("advance"), "decline": breadth.get("decline"),
        "n": breadth.get("n_total"),
        "ad10": _f(breadth.get("ad_ratio_10d")),
        "up_days_20": _f(breadth.get("up_days_20")),
        "data_date": breadth.get("data_date"),
        "hist": hist,
        "divergence": None,
        "usable": True,
    }
    # quá ít mã hoặc quá cũ -> không đưa vào chấm điểm
    try:
        lag = (pd.Timestamp(m["date"]).normalize() - pd.Timestamp(out["data_date"])).days if m else 0
    except Exception:
        lag = None
    out["lag_days"] = lag
    if (out["n"] or 0) < 100 or (lag is not None and lag > max_lag_days):
        out["usable"] = False

    # Phân kỳ: chỉ số đi một đằng, đa số cổ phiếu đi một nẻo
    if m and len(hist) >= 10:
        ad_trend = hist["ad_line"].iloc[-1] - hist["ad_line"].iloc[-10]
        roc = m.get("roc20") or 0
        p50 = out["pct50"] if out["pct50"] is not None else 50
        if roc > 0 and (ad_trend < 0 or p50 < 40):
            out["divergence"] = ("bearish",
                                 "⚠️ **Xanh vỏ đỏ lòng**: VN-Index tăng 20 phiên nhưng số mã giảm áp đảo / ít mã giữ được MA50 "
                                 "→ đà tăng dựa vào vài cổ phiếu trụ, rủi ro cao khi trụ hết lực.")
        elif roc < 0 and ad_trend > 0 and p50 >= 40:
            out["divergence"] = ("bullish",
                                 "🌱 **Phân kỳ dương**: VN-Index giảm nhưng số mã tăng lại nhiều hơn → dòng tiền đang âm thầm "
                                 "quay lại cổ phiếu, thường xuất hiện gần vùng tạo đáy.")
    return out


# ════════════════════════════════════════════════════════════════════
# 4. SỨC MẠNH TƯƠNG ĐỐI GIỮA CÁC NHÓM CHỈ SỐ
# ════════════════════════════════════════════════════════════════════
INDEX_LABELS = {"VNINDEX": "VN-Index", "VN30": "VN30 (vốn hoá lớn)",
                "HNXINDEX": "HNX-Index", "UPCOM": "UPCoM-Index"}


def relative_perf(dfs: dict, windows=(5, 20, 60)):
    """% thay đổi của từng chỉ số theo 1 tuần / 1 tháng / 3 tháng."""
    rows = []
    for sym, df in dfs.items():
        d = normalize_daily(df)
        if d is None or len(d) < 2:
            continue
        c = d["close"]
        row = {"Chỉ số": INDEX_LABELS.get(sym, sym), "_sym": sym, "Điểm": float(c.iloc[-1])}
        for w, name in zip(windows, ("1 tuần", "1 tháng", "3 tháng")):
            row[name] = _pct(c.iloc[-1], c.iloc[-1 - w]) if len(c) > w else None
        rows.append(row)
    return pd.DataFrame(rows)


def rotation_insight(rp):
    """Diễn giải: dòng tiền tập trung vào trụ (VN30) hay lan toả sang mid/small cap."""
    if rp is None or rp.empty or "_sym" not in rp.columns:
        return None
    r = rp.set_index("_sym")
    if "VN30" not in r.index or not ({"HNXINDEX", "UPCOM"} & set(r.index)):
        return None
    vn30 = _f(r.at["VN30", "1 tháng"])
    small = [_f(r.at[s, "1 tháng"]) for s in ("HNXINDEX", "UPCOM") if s in r.index]
    small = [x for x in small if x is not None]
    if vn30 is None or not small:
        return None
    gap = vn30 - sum(small) / len(small)
    if gap >= 2:
        return ("🏛️ **Dòng tiền tập trung vào vốn hoá lớn**: VN30 mạnh hơn nhóm HNX/UPCoM "
                f"{gap:.1f} điểm % trong 1 tháng. Nên ưu tiên cổ phiếu đầu ngành, hạn chế penny/midcap đầu cơ.")
    if gap <= -2:
        return ("🌊 **Dòng tiền lan toả sang mid/small cap**: HNX/UPCoM mạnh hơn VN30 "
                f"{-gap:.1f} điểm % trong 1 tháng. Khẩu vị rủi ro đang tăng — cơ hội ở nhóm vừa và nhỏ, "
                "nhưng cũng là dấu hiệu thị trường bắt đầu 'nóng'.")
    return ("⚖️ **Dòng tiền cân bằng** giữa vốn hoá lớn và nhóm vừa/nhỏ "
            f"(chênh lệch {gap:+.1f} điểm % trong 1 tháng).")


# ════════════════════════════════════════════════════════════════════
# 5. BẢNG CHẤM ĐIỂM -> TỶ TRỌNG
# ════════════════════════════════════════════════════════════════════
def _factor(group, name, value, pts, lo, hi, note):
    return {"Nhóm": group, "Tiêu chí": name, "Giá trị": value,
            "Điểm": int(pts), "Thang": f"{lo:+d}…{hi:+d}", "Ý nghĩa": note}


def score_market(m, regime, bview=None, pe=None):
    """Mỗi tiêu chí cho điểm có lý do rõ ràng. Tổng điểm -> tỷ trọng cổ phiếu 10–90%."""
    F = []
    if not m:
        return None
    p = m["price"]

    # ── XU HƯỚNG (-3..+3): điều quan trọng nhất, "đừng chống lại xu hướng"
    if m.get("ma200") is not None:
        above = p > m["ma200"]
        F.append(_factor("Xu hướng", "Giá so với MA200", f"{_pct(p, m['ma200']):+.1f}%", 1 if above else -1, -1, 1,
                         "Trên MA200 → xu hướng dài hạn tăng" if above else "Dưới MA200 → xu hướng dài hạn giảm"))
    if m.get("ma50") is not None:
        above = p > m["ma50"]
        F.append(_factor("Xu hướng", "Giá so với MA50", f"{_pct(p, m['ma50']):+.1f}%", 1 if above else -1, -1, 1,
                         "Trên MA50 → trung hạn tích cực" if above else "Dưới MA50 → trung hạn suy yếu"))
    if m.get("ma50_slope") is not None:
        up = m["ma50_slope"] > 0
        F.append(_factor("Xu hướng", "Độ dốc MA50 (10 phiên)", f"{m['ma50_slope']:+.2f}%", 1 if up else -1, -1, 1,
                         "MA50 dốc lên" if up else "MA50 dốc xuống — lực bán chiếm ưu thế trung hạn"))

    # ── ĐỘNG LƯỢNG (-2..+2)
    if m.get("macd_hist") is not None:
        pos = m["macd_hist"] > 0
        rising = m.get("macd_hist_prev") is not None and m["macd_hist"] > m["macd_hist_prev"]
        F.append(_factor("Động lượng", "MACD histogram", f"{m['macd_hist']:+.1f}", 1 if pos else -1, -1, 1,
                         ("MACD trên Signal" if pos else "MACD dưới Signal")
                         + (" và đang cải thiện" if rising else " và đang xấu đi")))
    rsi = m.get("rsi")
    if rsi is not None:
        if rsi >= 75:
            pts, note = -1, "Quá mua — dễ có nhịp chốt lời"
        elif rsi <= 30:
            pts, note = 1, "Quá bán — xác suất hồi kỹ thuật cao"
        elif rsi <= 35:
            pts, note = 0, "Gần vùng quá bán — có thể hồi nhưng chưa phải tín hiệu mua"
        elif rsi >= 50:
            pts, note = 0, "Trung tính nghiêng tích cực"
        else:
            pts, note = 0, "Trung tính nghiêng yếu"
        F.append(_factor("Động lượng", "RSI(14)", f"{rsi:.0f}", pts, -1, 1, note))

    # ── ÁP LỰC BÁN TỔ CHỨC (-2..+1)
    nd = m.get("dist_days", 0)
    if nd >= 6:
        pts, note = -2, "Rất nhiều phiên bán ra mạnh — tổ chức đang phân phối"
    elif nd >= 4:
        pts, note = -1, "Áp lực phân phối đáng chú ý"
    elif nd <= 2:
        pts, note = 1, "Ít phiên bán mạnh — cung không đáng lo"
    else:
        pts, note = 0, "Mức bình thường"
    F.append(_factor("Áp lực bán", f"Ngày phân phối ({DIST_WINDOW} phiên)", f"{nd} ngày", pts, -2, 1, note))
    if m.get("ftd"):
        f = m["ftd"]
        F.append(_factor("Áp lực bán", "Follow-Through Day", f"{f['date']:%d/%m} (+{f['gain']:.1f}%)", 1, 0, 1,
                         "Có phiên xác nhận đáy với thanh khoản tăng — nhịp hồi đáng tin hơn"))

    # ── ĐỘ RỘNG (-3..+3), chỉ khi dữ liệu đủ mới và đủ mã
    if bview and bview.get("usable"):
        p50 = bview.get("pct50")
        if p50 is not None:
            pts = 2 if p50 >= 60 else 1 if p50 >= 50 else 0 if p50 >= 40 else -1 if p50 >= 25 else -2
            F.append(_factor("Độ rộng", "% cổ phiếu trên MA50", f"{p50:.0f}%", pts, -2, 2,
                             "Đa số cổ phiếu khoẻ" if pts > 0 else
                             ("Phân hoá" if pts == 0 else "Đa số cổ phiếu đã gãy xu hướng trung hạn")))
        ad10 = bview.get("ad10")
        if ad10 is not None:
            pts = 1 if ad10 >= 1.2 else -1 if ad10 <= 0.8 else 0
            F.append(_factor("Độ rộng", "Tỷ lệ mã tăng/giảm 10 phiên", f"{ad10:.2f}", pts, -1, 1,
                             "Bên mua lan toả" if pts > 0 else ("Bên bán lan toả" if pts < 0 else "Cân bằng")))
        if bview.get("divergence"):
            kind = bview["divergence"][0]
            F.append(_factor("Độ rộng", "Phân kỳ chỉ số – độ rộng", "Âm" if kind == "bearish" else "Dương",
                             -1 if kind == "bearish" else 1, -1, 1,
                             "Chỉ số tăng nhờ trụ" if kind == "bearish" else "Cổ phiếu khoẻ hơn chỉ số"))

    # ── ĐỊNH GIÁ (-2..+2): tác động chậm, chỉ là "đệm an toàn"
    pct = _f((pe or {}).get("percentile"))
    if pct is not None:
        pts = 2 if pct < 20 else 1 if pct < 35 else -2 if pct > 80 else -1 if pct > 65 else 0
        F.append(_factor("Định giá", "P/E VN-Index (percentile lịch sử)",
                         f"{_f(pe.get('pe_now'), 0):.1f}x · {pct:.0f}%", pts, -2, 2,
                         "Rẻ so với lịch sử — biên an toàn tốt" if pts > 0 else
                         ("Đắt so với lịch sử" if pts < 0 else "Định giá hợp lý")))

    # ── THANH KHOẢN XÁC NHẬN (-1..+1)
    vr, chg = m.get("vol_ratio"), m.get("chg_pct")
    if vr is not None and chg is not None:
        if vr >= 1.2 and chg > 0:
            pts, note = 1, "Phiên tăng có thanh khoản cao — tiền vào thật"
        elif vr >= 1.2 and chg < 0:
            pts, note = -1, "Phiên giảm có thanh khoản cao — bán tháo"
        else:
            pts, note = 0, "Thanh khoản không xác nhận rõ xu hướng phiên"
        F.append(_factor("Thanh khoản", "KL phiên / TB20", f"{vr:.2f}x ({chg:+.2f}%)", pts, -1, 1, note))

    total = sum(f["Điểm"] for f in F)
    # Pha thị trường là "trần/sàn" cho tỷ trọng: không cho phép 80-90% cổ phiếu khi đang downtrend
    equity = int(min(max(round((50 + 4 * total) / 10) * 10, 10), 90))
    cap = {"downtrend": 40, "pullback": 70, "recovery": 70}.get(regime)
    floor = {"uptrend": 40}.get(regime)
    if cap is not None:
        equity = min(equity, cap)
    if floor is not None:
        equity = max(equity, floor)

    if equity >= 80:
        action, color = "TẤN CÔNG — giữ tỷ trọng cao, mua theo xu hướng", "success"
    elif equity >= 60:
        action, color = "TÍCH CỰC — mua có chọn lọc cổ phiếu khoẻ", "success"
    elif equity >= 50:
        action, color = "TRUNG TÍNH — giữ, chỉ mua ở điểm đẹp", "info"
    elif equity >= 30:
        action, color = "THẬN TRỌNG — hạ dần tỷ trọng, không mua đuổi", "warning"
    else:
        action, color = "PHÒNG THỦ — ưu tiên tiền mặt, chờ tín hiệu đáy", "danger"

    return {"factors": F, "total": total, "equity": equity, "cash": 100 - equity,
            "action": action, "color": color, "cap": cap, "floor": floor}


# ════════════════════════════════════════════════════════════════════
# 6. KẾT LUẬN & MỐC THEO DÕI
# ════════════════════════════════════════════════════════════════════
def _lc(text):
    """Viết thường chữ đầu nhưng giữ nguyên từ viết tắt (MA50, MACD, RSI...)."""
    if not text:
        return text
    first = text.split(" ", 1)[0]
    return text if first.isupper() or any(ch.isdigit() for ch in first) else text[0].lower() + text[1:]


def headline(m, regime, sc, bview=None):
    """1–2 câu tóm tắt: pha + yếu tố tốt nhất + yếu tố xấu nhất + tỷ trọng."""
    if not m or not sc:
        return "Chưa đủ dữ liệu để đưa ra nhận định."
    label = REGIMES[regime][0].split(" ", 1)[1].lower()
    pos = sorted([f for f in sc["factors"] if f["Điểm"] > 0], key=lambda f: -f["Điểm"])
    neg = sorted([f for f in sc["factors"] if f["Điểm"] < 0], key=lambda f: f["Điểm"])
    parts = [f"VN-Index **{m['price']:,.2f}** đang ở pha **{label}**, cách đỉnh 52 tuần "
             f"**{m['dd_from_high']:.1f}%**."]
    if pos and neg:
        parts.append(f"Điểm sáng: {_lc(pos[0]['Ý nghĩa'])}; điểm trừ lớn nhất: {_lc(neg[0]['Ý nghĩa'])}.")
    elif neg:
        parts.append(f"Hầu hết tín hiệu tiêu cực, nặng nhất: {_lc(neg[0]['Ý nghĩa'])}.")
    elif pos:
        parts.append(f"Hầu hết tín hiệu tích cực, nổi bật: {_lc(pos[0]['Ý nghĩa'])}.")
    parts.append(f"Gợi ý tỷ trọng cổ phiếu khoảng **{sc['equity']}%**.")
    return " ".join(parts)


def key_levels(m):
    """Các mốc giá quan trọng quanh giá hiện tại, sắp xếp từ cao xuống thấp."""
    if not m:
        return pd.DataFrame()
    p = m["price"]
    lv = [("Đỉnh 52 tuần", m.get("high52")), ("Kháng cự 20 phiên", m.get("resist20")),
          ("MA20", m.get("ma20")), ("MA50", m.get("ma50")), ("MA200", m.get("ma200")),
          ("Hỗ trợ 20 phiên", m.get("support20")), ("Hỗ trợ 60 phiên", m.get("support60")),
          ("Đáy 52 tuần", m.get("low52"))]
    seen, uniq = set(), []
    for n, v in lv:  # bỏ mốc trùng giá trị (vd hỗ trợ 60 phiên = đáy 52 tuần)
        if v is not None and round(v, 1) not in seen:
            seen.add(round(v, 1))
            uniq.append((n, v))
    lv = uniq
    rows = [{"Mốc": n, "Điểm": v, "Cách giá": _pct(v, p),
             "Vai trò": "Kháng cự" if v > p else "Hỗ trợ"} for n, v in lv if v is not None]
    return pd.DataFrame(rows).sort_values("Điểm", ascending=False).reset_index(drop=True)


def watch_levels(m, regime):
    """Kịch bản hành động: điều gì phải xảy ra để NÂNG / HẠ tỷ trọng."""
    if not m:
        return []
    p = m["price"]
    above = sorted([v for v in (m.get("ma20"), m.get("ma50"), m.get("ma200"), m.get("resist20")) if v and v > p])
    # giá đang ở sát đáy 20 phiên -> mốc hỗ trợ có ý nghĩa tiếp theo là đáy 60 phiên / 52 tuần
    cands = [m.get("ma20"), m.get("ma50"), m.get("ma200"), m.get("support20"), m.get("support60"), m.get("low52")]
    below = sorted([v for v in cands if v and v < p * 0.995], reverse=True)
    out = []
    if above:
        r = above[0]
        name = next(n for n, v in (("MA20", m.get("ma20")), ("MA50", m.get("ma50")), ("MA200", m.get("ma200")),
                                   ("kháng cự 20 phiên", m.get("resist20"))) if v == r)
        out.append(("up", f"**Nâng tỷ trọng** nếu VN-Index đóng cửa vượt **{r:,.0f}** ({name}, "
                          f"+{_pct(r, p):.1f}%) với thanh khoản ≥ trung bình 20 phiên."))
    if below:
        s = below[0]
        name = next(n for n, v in (("MA20", m.get("ma20")), ("MA50", m.get("ma50")), ("MA200", m.get("ma200")),
                                   ("hỗ trợ 20 phiên", m.get("support20")), ("hỗ trợ 60 phiên", m.get("support60")),
                                   ("đáy 52 tuần", m.get("low52"))) if v == s)
        out.append(("down", f"**Hạ tỷ trọng** nếu đóng cửa thủng **{s:,.0f}** ({name}, {_pct(s, p):.1f}%)."))
    if regime in ("downtrend", "pullback") and not m.get("ftd"):
        out.append(("info", "Chờ **Follow-Through Day** (phiên tăng ≥ 1,2% với thanh khoản tăng, từ ngày thứ 4 "
                            "của nhịp hồi) trước khi giải ngân mạnh trở lại."))
    if m.get("dist_days", 0) >= 4 and regime in ("uptrend", "recovery"):
        out.append(("down", f"Đã có **{m['dist_days']} ngày phân phối** trong {DIST_WINDOW} phiên — "
                            "thêm 1–2 phiên nữa là tín hiệu đỉnh ngắn hạn, không mua đuổi."))
    return out
