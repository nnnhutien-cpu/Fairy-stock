# File: market_trend_signal.py
"""
Tín hiệu xu hướng VN-INDEX dựa trên Ichimoku — THAY THẾ HOÀN TOÀN
logic Score/A-D/tỷ trọng CP-Tiền mặt cũ (market_score.py, KHÔNG dùng nữa).

Lý do thay: khối "MUA/GIỮ - Score - Tỷ trọng CP/Tiền mặt" cũ tự chấm điểm
từ nhiều chỉ báo cộng dồn, không bám sát 1 hệ quy tắc rõ ràng nên ra kết
quả mâu thuẫn với chính cảnh báo "thị trường suy yếu" hiển thị cạnh nó.

Logic mới: dùng ĐÚNG bộ quy tắc Ichimoku đã có sẵn và đang chạy ổn định
trong backtester.py (calculate_ichimoku_daily + phần lõi của
run_ichimoku_backtest_daily), áp dụng cho chính VN-INDEX thay vì từng mã:

  MUA / VÀO TREND TĂNG khi TẤT CẢ đúng:
    - Giá đóng cửa phá lên trên đỉnh mây Kumo (isAboveCloud)
    - Khối lượng >= 120% trung bình 20 phiên (isVolOk)
    - Tenkan-sen > Kijun-sen, tức momentum đang hướng lên (isMomentumUp)
    - Giá vẫn ở trên đáy mây, chưa gãy trend (isNotDowntrend)

  BÁN / ĐỨNG NGOÀI khi ĐANG Ở TRONG TREND và MỘT TRONG HAI đúng:
    - Giá đóng cửa gãy xuống dưới Kijun-sen
    - Giá đóng cửa gãy xuống dưới đáy mây Kumo

Không còn khái niệm "Score", "Tỷ trọng CP %", "Tiền mặt %" nữa — thay
bằng 1 trạng thái nhị phân rõ ràng: đang TRONG TREND TĂNG hay ĐỨNG NGOÀI,
kèm điểm vào/ra gần nhất (giống hệt phong cách hiển thị ở ảnh mẫu).
"""

import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrendSignal:
    in_trend: bool                 # True = đang trong trend tăng (đã MUA), False = đứng ngoài
    current_price: float
    current_date: str
    entry_date: Optional[str] = None
    entry_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_change_pct: Optional[float] = None
    exit_reason: Optional[str] = None


def calculate_ichimoku(df: pd.DataFrame, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """
    Giống hệt calculate_ichimoku_daily() trong backtester.py — dùng lại
    để đảm bảo tín hiệu VN-INDEX nhất quán với tín hiệu từng mã cổ phiếu.
    """
    if df is None or len(df) < p_senkou_b + p_shift:
        return None

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    df['Tenkan'] = (df['high'].rolling(window=p_tenkan).max() + df['low'].rolling(window=p_tenkan).min()) / 2
    df['Kijun'] = (df['high'].rolling(window=p_kijun).max() + df['low'].rolling(window=p_kijun).min()) / 2
    senkou_a_raw = (df['Tenkan'] + df['Kijun']) / 2
    df['Senkou_A'] = senkou_a_raw.shift(p_shift)
    senkou_b_raw = (df['high'].rolling(window=p_senkou_b).max() + df['low'].rolling(window=p_senkou_b).min()) / 2
    df['Senkou_B'] = senkou_b_raw.shift(p_shift)
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()

    df.dropna(subset=['Senkou_A', 'Senkou_B', 'Vol_MA20', 'Tenkan', 'Kijun'], inplace=True)
    df = df.reset_index(drop=True)
    return df if not df.empty else None


def get_trend_signal(df: pd.DataFrame, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26) -> Optional[TrendSignal]:
    """
    Chạy toàn bộ lịch sử để xác định trạng thái HIỆN TẠI (trong trend hay đứng ngoài)
    + điểm vào/ra gần nhất, dùng đúng quy tắc MUA/BÁN của backtester.py.
    `df` cần có cột: time (hoặc date), open, high, low, close, volume — của VN-INDEX.
    """
    ich = calculate_ichimoku(df, p_tenkan, p_kijun, p_senkou_b, p_shift)
    if ich is None or len(ich) < 2:
        return None

    time_col = 'time' if 'time' in ich.columns else ('date' if 'date' in ich.columns else None)

    def fmt_date(d):
        d = pd.to_datetime(d)
        return d.strftime('%d/%m/%y')

    in_trend = False
    entry_date, entry_price = None, None
    last_exit_date, last_exit_price, last_exit_change_pct, last_exit_reason = None, None, None, None

    for i in range(1, len(ich)):
        close = ich['close'].iloc[i]
        vol = ich['volume'].iloc[i]
        vol_ma20 = ich['Vol_MA20'].iloc[i]
        tenkan = ich['Tenkan'].iloc[i]
        kijun = ich['Kijun'].iloc[i]
        senkou_a = ich['Senkou_A'].iloc[i]
        senkou_b = ich['Senkou_B'].iloc[i]
        cloud_top = max(senkou_a, senkou_b)
        cloud_bot = min(senkou_a, senkou_b)

        is_above_cloud = close > cloud_top
        is_vol_ok = vol >= (vol_ma20 * 1.2)
        is_momentum_up = tenkan > kijun
        is_not_downtrend = close >= cloud_bot

        date_val = ich[time_col].iloc[i] if time_col else i

        if not in_trend:
            if is_above_cloud and is_vol_ok and is_momentum_up and is_not_downtrend:
                in_trend = True
                entry_date = fmt_date(date_val)
                entry_price = close
        else:
            sell_reason = None
            if close < kijun:
                sell_reason = "cắt xuống Kijun-sen"
            elif close < cloud_bot:
                sell_reason = "gãy đáy mây Kumo"

            if sell_reason:
                last_exit_date = fmt_date(date_val)
                last_exit_price = close
                last_exit_change_pct = round((close - entry_price) / entry_price * 100, 2)
                last_exit_reason = sell_reason
                in_trend = False
                entry_date, entry_price = None, None

    last_row = ich.iloc[-1]
    current_price = last_row['close']
    current_date = fmt_date(last_row[time_col]) if time_col else ""

    return TrendSignal(
        in_trend=in_trend,
        current_price=current_price,
        current_date=current_date,
        entry_date=entry_date,
        entry_price=entry_price,
        exit_date=last_exit_date,
        exit_price=last_exit_price,
        exit_change_pct=last_exit_change_pct,
        exit_reason=last_exit_reason,
    )


def render_trend_signal(df: pd.DataFrame, index_name: str = "VNINDEX",
                         p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """
    Vẽ khối trạng thái tín hiệu trong Streamlit — THAY THẾ hoàn toàn khối
    'Khuyến nghị hành động / MUA-GIỮ / Score / Tỷ trọng CP' cũ.
    Gọi hàm này trong render_market_tab() (ui_layout.py) thay cho lời gọi
    render_market_recommendation() cũ.
    """
    import streamlit as st

    signal = get_trend_signal(df, p_tenkan, p_kijun, p_senkou_b, p_shift)

    if signal is None:
        st.info("📡 Chưa đủ dữ liệu lịch sử để tính tín hiệu Ichimoku (cần tối thiểu ~80 phiên).")
        return None

    status_label = "🟢 TRONG TREND TĂNG" if signal.in_trend else "⚪ ĐỨNG NGOÀI"
    st.markdown(f"### {status_label} · {index_name} @ {signal.current_price:,.2f}")

    if signal.in_trend and signal.entry_date:
        change_pct = round((signal.current_price - signal.entry_price) / signal.entry_price * 100, 2)
        st.success(
            f"🟢 Điểm vào {signal.entry_date} tại {signal.entry_price:,.2f} "
            f"— hiện tại {change_pct:+.1f}% — đang giữ vị thế theo trend tăng."
        )
    elif signal.exit_date:
        st.warning(
            f"🔴 Đã thoát tại {signal.exit_date}, giá {signal.exit_price:,.2f} "
            f"({signal.exit_change_pct:+.1f}%) — {signal.exit_reason} — đứng ngoài chờ trend tăng mới."
        )
    else:
        st.info("⚪ Chưa ghi nhận tín hiệu MUA nào trong dữ liệu hiện có — đứng ngoài quan sát.")

    st.caption(
        "Tín hiệu THAM KHẢO (Ichimoku): vào khi phá mây + volume ≥120% MA20 + Tenkan>Kijun; "
        "thoát khi đóng cửa dưới Kijun-sen hoặc dưới đáy mây."
    )

    return signal
