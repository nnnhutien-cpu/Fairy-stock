"""
accumulation_signals.py
------------------------
Lập trình hoá các quy tắc volume/tích luỹ trong tài liệu "Volume: Bài học về
thanh khoản" thành tín hiệu tự động, để gắn vào tab "🕰️ Tích Lũy" đã có sẵn
trong app (không phải tab mới).

Yêu cầu cột trong DataFrame đầu vào (đã lowercase, giống chuẩn trong
main.py / data_loader.py): 'close', 'high', 'low', 'volume', và tuỳ chọn
'time'.

Cách dùng gợi ý trong main.py, bên trong `with tab_tich_luy:` (bạn tự thêm
biến tab này vào st.tabs(...) hiện có):

    from accumulation_signals import analyze_accumulation

    df = get_stock_data(ticker_tl)              # dữ liệu daily có sẵn
    result = analyze_accumulation(df)

    st.metric("Trạng thái Volume", result["trang_thai"])
    st.write(result["giai_thich"])
    if result["rsi"] is not None:
        st.metric("RSI", f"{result['rsi']:.1f}")
"""

import numpy as np
import pandas as pd


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def analyze_accumulation(df: pd.DataFrame, vol_ma_period: int = 20) -> dict:
    """
    Áp dụng quy tắc trong tài liệu:
    - Volume tăng 1.5-2 lần MA20  -> có thể là chân sóng lớn / cảnh báo đỉnh
      sóng con trong vùng tích luỹ (bán bớt tối thiểu 50%).
    - Volume giảm mạnh (<50% MA20) -> vùng kiệt cung, ưu tiên MUA.
    - Volume tăng mạnh vượt MA20 ~30% trở lên trong khi RSI > 70 -> cảnh báo
      vùng phân phối / nên bán.
    - RSI < 30 -> vùng mua theo chỉ báo.

    Trả về dict:
        trang_thai:  Nhãn ngắn gọn ("TÍCH LUỸ - VÙNG MUA", "CẢNH BÁO BÁN", ...)
        giai_thich:  Câu giải thích theo đúng logic tài liệu.
        vol_ratio:   Tỷ lệ volume hiện tại / MA20.
        rsi:         Giá trị RSI mới nhất (hoặc None nếu không đủ dữ liệu).
    """
    if df is None or df.empty or "volume" not in df.columns:
        return {
            "trang_thai": "KHÔNG ĐỦ DỮ LIỆU",
            "giai_thich": "Thiếu dữ liệu volume để phân tích.",
            "vol_ratio": None,
            "rsi": None,
        }

    df = df.copy()
    df["vol_ma20"] = df["volume"].rolling(vol_ma_period).mean()
    df["rsi"] = _rsi(df["close"]) if "close" in df.columns else np.nan

    last = df.iloc[-1]
    vol_ma20 = last["vol_ma20"]
    if pd.isna(vol_ma20) or vol_ma20 == 0:
        return {
            "trang_thai": "KHÔNG ĐỦ DỮ LIỆU",
            "giai_thich": f"Cần tối thiểu {vol_ma_period} phiên để tính MA volume.",
            "vol_ratio": None,
            "rsi": None,
        }

    vol_ratio = last["volume"] / vol_ma20
    rsi_val = last["rsi"] if "rsi" in last and not pd.isna(last["rsi"]) else None

    # --- Áp quy tắc theo thứ tự ưu tiên của tài liệu ---
    if vol_ratio <= 0.5:
        trang_thai = "TÍCH LUỸ - VÙNG MUA (kiệt cung)"
        giai_thich = (
            f"Volume hiện tại chỉ bằng {vol_ratio:.0%} MA{vol_ma_period} "
            "(dưới 50%) — đây là dấu hiệu kiệt cung, theo tài liệu là thời "
            "điểm mua phù hợp nhất trong giai đoạn tích luỹ."
        )
    elif vol_ratio >= 1.3 and rsi_val is not None and rsi_val >= 70:
        trang_thai = "CẢNH BÁO PHÂN PHỐI - NÊN BÁN"
        giai_thich = (
            f"Volume vượt MA{vol_ma_period} khoảng {vol_ratio:.0%} kèm RSI "
            f"{rsi_val:.0f} (>70). Kết hợp này khớp mô tả 'cây Phân phối': "
            "khối lượng tăng mạnh nhưng là đỉnh, báo hiệu giảm giá."
        )
    elif 1.5 <= vol_ratio <= 2.0:
        trang_thai = "CHÂN SÓNG LỚN / CẢNH BÁO ĐỈNH SÓNG CON - CÂN NHẮC BÁN BỚT"
        giai_thich = (
            f"Volume tăng {vol_ratio:.1f} lần MA{vol_ma_period} (trong biên "
            "1.5–2 lần). Theo tài liệu, đây có thể là chân của một con sóng "
            "lớn NHƯNG cũng có thể là đỉnh sóng con trong vùng tích luỹ — "
            "nên bán bớt tối thiểu 50% nếu đang trong vùng tích luỹ đã xác "
            "nhận, và theo dõi thêm biến động giá/RSI để phân biệt."
        )
    elif rsi_val is not None and rsi_val <= 30:
        trang_thai = "VÙNG MUA THEO RSI"
        giai_thich = f"RSI hiện tại {rsi_val:.0f} (<30) — vùng quá bán, cân nhắc mua theo chỉ báo."
    else:
        trang_thai = "TRUNG TÍNH - CHƯA CÓ TÍN HIỆU RÕ"
        giai_thich = (
            f"Volume ~{vol_ratio:.1f} lần MA{vol_ma_period}"
            + (f", RSI {rsi_val:.0f}" if rsi_val is not None else "")
            + ". Chưa khớp ngưỡng nào trong quy tắc — nên chờ thêm tín hiệu."
        )

    return {
        "trang_thai": trang_thai,
        "giai_thich": giai_thich,
        "vol_ratio": round(float(vol_ratio), 3),
        "rsi": round(float(rsi_val), 2) if rsi_val is not None else None,
    }


def classify_breakdown_pattern(df: pd.DataFrame, support_level: float) -> str:
    """
    Phân loại 3 dạng phá vùng hỗ trợ trong giai đoạn tích luỹ (Loại 1/2/3
    theo tài liệu). Cần truyền vào support_level (vùng hỗ trợ đang xét).
    Trả về một trong: "LOAI_1_BAN", "LOAI_2_MUA", "LOAI_3_MUA", "KHONG_RO".
    """
    if df is None or len(df) < 21 or "close" not in df.columns:
        return "KHONG_RO"

    df = df.copy()
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    prev_avg_vol = df["vol_ma20"].iloc[-2]
    last = df.iloc[-1]
    prev = df.iloc[-2]

    broke_support = last["low"] < support_level or prev["low"] < support_level
    if not broke_support:
        return "KHONG_RO"

    vol_spike = last["volume"] / prev_avg_vol if prev_avg_vol else 0
    spread = last["high"] - last["low"]
    closed_low = spread > 0 and (last["close"] - last["low"]) / spread < 0.25
    recovered_half = spread > 0 and (last["close"] - last["low"]) / spread >= 0.5

    if vol_spike >= 2.0 and closed_low:
        return "LOAI_1_BAN"
    elif vol_spike >= 1.3 and recovered_half:
        return "LOAI_2_MUA"
    elif vol_spike < 1.1 and spread < df["close"].iloc[-20:].std():
        return "LOAI_3_MUA"
    return "KHONG_RO"
