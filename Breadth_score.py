"""
breadth_score.py
Tính điểm Breadth (độ rộng thị trường) cho ~400 mã sàn HOSE.

THIẾT KẾ: 2 trụ cột ĐỘC LẬP cộng lại thành tổng điểm Breadth (-8 đến +8):

1) AD_Score (-4..+4)
   Dựa trên % mã TĂNG GIÁ trong phiên hôm nay (Advance/Decline %).
   -> Phản ứng nhanh với tâm lý thị trường trong ngày, NHƯNG dễ nhiễu
      (1 phiên xả hàng bất thường có thể làm số này rơi mạnh dù xu hướng
      trung hạn vẫn tốt).

2) Trend_Breadth_Score (-4..+4)
   Dựa trên % mã đang nằm TRÊN đường MA50.
   -> Đo "sức khỏe cấu trúc" trung hạn của toàn thị trường. Mượt hơn nhiều,
      không đổi chiều chỉ vì một phiên biến động ngắn hạn.

Lý do tách 2 trụ cột thay vì gộp thành 1 con số A/D duy nhất (như bản gốc):
- Tránh để MỘT phiên bất thường (tốt hoặc xấu) lật ngược toàn bộ khuyến
  nghị phân bổ vốn -> tránh vào/ra thị trường liên tục theo nhiễu, tốn phí
  và dễ bị "quét" hai chiều.
- Vẫn giữ được độ nhạy (qua AD_Score) để bắt sớm các phiên đảo chiều mạnh
  thật sự (khi cả 2 trụ cột cùng xấu đi).
"""

from __future__ import annotations
import pandas as pd


def compute_ad_score(ad_pct: float) -> int:
    """Điểm từ % mã tăng giá trong phiên (Advance/Decline), khung -4..+4."""
    if ad_pct >= 75: return 4
    if ad_pct >= 60: return 3
    if ad_pct >= 50: return 2
    if ad_pct >= 42: return 1
    if ad_pct >= 35: return 0
    if ad_pct >= 25: return -1
    if ad_pct >= 18: return -2
    if ad_pct >= 10: return -3
    return -4


def compute_trend_breadth_score(pct_above_ma50: float) -> int:
    """Điểm từ % mã đang > MA50, khung -4..+4 (chỉ báo cấu trúc, ít nhiễu hơn AD)."""
    if pct_above_ma50 >= 75: return 4
    if pct_above_ma50 >= 60: return 3
    if pct_above_ma50 >= 50: return 2
    if pct_above_ma50 >= 40: return 1
    if pct_above_ma50 >= 30: return 0
    if pct_above_ma50 >= 20: return -1
    if pct_above_ma50 >= 12: return -2
    if pct_above_ma50 >= 6:  return -3
    return -4


def compute_breadth_metrics(symbols_data: pd.DataFrame) -> dict:
    """
    symbols_data: DataFrame 1 dòng / mã, các cột bắt buộc:
      - change_pct  : % thay đổi giá phiên hôm nay
      - above_ma20  : bool, giá đóng cửa > MA20
      - above_ma50  : bool, giá đóng cửa > MA50
    """
    total = len(symbols_data)
    if total == 0:
        return {
            "n_total": 0, "ad_pct": 0, "pct_above_ma20": 0, "pct_above_ma50": 0,
            "ad_score": 0, "trend_breadth_score": 0, "breadth_score": 0,
        }

    adv = int((symbols_data["change_pct"] > 0).sum())
    ad_pct = round(adv / total * 100, 1)
    pct_above_ma20 = round(float(symbols_data["above_ma20"].sum()) / total * 100, 1)
    pct_above_ma50 = round(float(symbols_data["above_ma50"].sum()) / total * 100, 1)

    ad_score = compute_ad_score(ad_pct)
    trend_breadth_score = compute_trend_breadth_score(pct_above_ma50)

    return {
        "n_total": total,
        "n_advance": adv,
        "ad_pct": ad_pct,
        "pct_above_ma20": pct_above_ma20,
        "pct_above_ma50": pct_above_ma50,
        "ad_score": ad_score,
        "trend_breadth_score": trend_breadth_score,
        "breadth_score": ad_score + trend_breadth_score,   # -8 .. +8
    }


def breadth_momentum_note(history: list, lookback_days: int = 5):
    """
    So sánh % mã trên MA50 hôm nay với N phiên trước để cảnh báo SỚM xu hướng
    breadth đang tốt lên / xấu đi, trước khi bucket điểm kịp đổi.
    `history`: list các dict breadth cũ (có key 'date' và 'pct_above_ma50'),
    mới nhất nằm ở CUỐI danh sách.
    """
    if len(history) <= lookback_days:
        return None
    today = history[-1]["pct_above_ma50"]
    past = history[-1 - lookback_days]["pct_above_ma50"]
    diff = today - past
    if diff >= 10:
        return f"📈 Breadth đang CẢI THIỆN nhanh: %mã>MA50 tăng {diff:+.1f} điểm % trong {lookback_days} phiên."
    if diff <= -10:
        return f"📉 Breadth đang XẤU ĐI nhanh: %mã>MA50 giảm {diff:+.1f} điểm % trong {lookback_days} phiên."
    return None


def score_to_allocation(total_score: int) -> dict:
    """
    Quy đổi TỔNG SCORE sang tỷ trọng Cổ phiếu / Tiền mặt + hành động khuyến nghị.

    TỔNG SCORE = Breadth[-8..8]  (module này)
               + PTKT[-5..5]     (Trend MA20 -2..2, RSI -1..1, MACD -1..1, Volume -1..1 — giữ nguyên logic đang có)
               + P/E[-2..2]      (theo percentile 20 năm — giữ nguyên logic đang có)
               = khung -15 .. +15
    """
    table = [
        (12,  85, "🔥 MUA CỰC MẠNH",        "success"),
        (9,   75, "🚀 MUA MẠNH",             "success"),
        (6,   65, "🟢 MUA TÍCH CỰC",         "success"),
        (3,   58, "🟢 MUA / GIỮ",            "success"),
        (1,   52, "🟢 GIỮ CAO",              "success"),
        (-1,  50, "➖ CÂN BẰNG",             "info"),
        (-3,  42, "🟠 GIẢM NHẸ",             "warning"),
        (-6,  30, "⚠️ GIẢM TỶ TRỌNG",        "warning"),
        (-9,  20, "🔴 PHÒNG THỦ",             "danger"),
        (-12, 10, "🛡️ PHÒNG THỦ MẠNH",       "danger"),
    ]
    for threshold, stock_pct, action, color in table:
        if total_score >= threshold:
            return {"score": total_score, "stock": stock_pct, "cash": 100 - stock_pct,
                     "action": action, "color": color}
    return {"score": total_score, "stock": 5, "cash": 95,
             "action": "💀 THOÁT KHỎI THỊ TRƯỜNG (CẦN GIẢI CỨU)", "color": "danger"}
