# File: market_score.py
"""
Module tính "Nhịp Đập Thị Trường": Score tổng hợp + khuyến nghị phân bổ
Cổ phiếu / Tiền mặt, dựa trên độ rộng thị trường (A/D) và cấu trúc (MA50).

SỬA LỖI CHÍNH so với bản cũ:
- Bản cũ: Score được cộng dồn từ nhiều chỉ báo (momentum, MA50...) và
  ngưỡng quy đổi Score -> tỷ trọng quá "rộng rãi" (Score dương là cho
  60% CP), nên dù A/D chỉ 13.5% (thị trường rất yếu) vẫn ra khuyến nghị
  MUA/GIỮ 60% cổ phiếu -> mâu thuẫn với chính cảnh báo "thị trường suy yếu"
  hiển thị ngay phía trên.
- Bản mới: A/D% đóng vai trò "công tắc an toàn" (safety gate) độc lập.
  Nếu A/D% quá thấp, tỷ trọng cổ phiếu bị CHẶN TRẦN cứng, bất kể Score
  tổng hợp là bao nhiêu. Score chỉ quyết định tỷ trọng CP trong PHẠM VI
  đã được A/D cho phép, không thể vượt trần.
"""

from dataclasses import dataclass


@dataclass
class MarketSnapshot:
    ad_pct: float          # % mã tăng giá trong phiên (Advance/Decline), 0-100
    above_ma50_pct: float  # % mã đang nằm trên đường MA50, 0-100
    momentum_score: int    # điểm momentum phụ (VD: thay đổi độ rộng so với hôm qua), có thể âm


# ==========================================
# 1. CÔNG TẮC AN TOÀN THEO ĐỘ RỘNG THỊ TRƯỜNG (A/D)
# ==========================================
# Mỗi ngưỡng A/D% quy định TRẦN tỷ trọng cổ phiếu tối đa được phép đề xuất.
# Đây là điều kiện chặn cứng — Score dương đến đâu cũng không được vượt trần này.
AD_CAP_TABLE = [
    # (A/D% tối thiểu,  Trần tỷ trọng CP tối đa,  Nhãn)
    (70, 100, "Thị trường rất khỏe, đa số mã tăng giá"),
    (55,  80, "Thị trường khỏe, phe mua chiếm ưu thế"),
    (40,  60, "Thị trường cân bằng, phân hoá"),
    (25,  35, "Thị trường suy yếu, số mã giảm giá chiếm ưu thế"),
    (0,   15, "Thị trường rất yếu, đa số mã giảm giá"),
]


def get_ad_cap(ad_pct: float):
    """Trả về (trần tỷ trọng CP tối đa, nhãn mô tả) dựa trên A/D%."""
    for threshold, cap, label in AD_CAP_TABLE:
        if ad_pct >= threshold:
            return cap, label
    return AD_CAP_TABLE[-1][1], AD_CAP_TABLE[-1][2]


# ==========================================
# 2. TÍNH SCORE TỔNG HỢP (trong phạm vi được A/D cho phép)
# ==========================================
def compute_market_score(snap: MarketSnapshot) -> int:
    """
    Score tổng hợp từ cấu trúc kỹ thuật + momentum.
    Score CHỈ dùng để định vị tỷ trọng CP bên TRONG trần đã cho phép bởi A/D,
    không dùng để phá vỡ trần đó.
    """
    score = 0

    # Cấu trúc: % mã trên MA50
    if snap.above_ma50_pct >= 60:
        score += 3
    elif snap.above_ma50_pct >= 40:
        score += 1
    elif snap.above_ma50_pct >= 25:
        score -= 1
    else:
        score -= 3

    # Độ rộng A/D cũng đóng góp vào Score (không chỉ làm trần)
    if snap.ad_pct >= 55:
        score += 3
    elif snap.ad_pct >= 40:
        score += 1
    elif snap.ad_pct >= 25:
        score -= 1
    else:
        score -= 3

    # Momentum phụ (VD: xu hướng độ rộng so với phiên trước)
    score += snap.momentum_score

    return score


# ==========================================
# 3. QUY ĐỔI SCORE -> TỶ TRỌNG CP, GIỚI HẠN BỞI TRẦN A/D
# ==========================================
def score_to_raw_allocation(score: int) -> int:
    """Quy đổi Score thô sang tỷ trọng CP mong muốn (chưa bị chặn trần)."""
    if score >= 6:
        return 90
    elif score >= 3:
        return 75
    elif score >= 0:
        return 60
    elif score >= -3:
        return 40
    elif score >= -6:
        return 20
    else:
        return 0


def get_recommendation(snap: MarketSnapshot) -> dict:
    """
    Trả về khuyến nghị hành động cuối cùng, đã áp trần an toàn theo A/D.
    Đây là hàm chính để gọi từ UI.
    """
    score = compute_market_score(snap)
    raw_allocation = score_to_raw_allocation(score)

    ad_cap, ad_label = get_ad_cap(snap.ad_pct)

    # ÁP TRẦN: tỷ trọng CP cuối cùng không bao giờ vượt trần cho phép bởi A/D
    final_stock_pct = min(raw_allocation, ad_cap)
    final_cash_pct = 100 - final_stock_pct

    was_capped = raw_allocation > ad_cap

    if final_stock_pct >= 65:
        action_label = "MUA/GIỮ"
        action_color = "green"
    elif final_stock_pct >= 35:
        action_label = "GIỮ/QUAN SÁT"
        action_color = "yellow"
    else:
        action_label = "GIẢM TỶ TRỌNG/PHÒNG THỦ"
        action_color = "red"

    return {
        "score": score,
        "raw_allocation_pct": raw_allocation,
        "stock_pct": final_stock_pct,
        "cash_pct": final_cash_pct,
        "was_capped_by_breadth": was_capped,
        "ad_cap_pct": ad_cap,
        "market_condition_label": ad_label,
        "action_label": action_label,
        "action_color": action_color,
    }


# ==========================================
# 4. HÀM RENDER STREAMLIT (gắn vào ui_layout.py -> render_market_tab)
# ==========================================
def render_market_recommendation(ad_pct: float, above_ma50_pct: float, momentum_score: int = 0):
    """
    Vẽ khối 'Khuyến nghị hành động' trong Streamlit, dùng logic đã fix ở trên.
    Gọi hàm này bên trong render_market_tab() của ui_layout.py, ngay sau
    phần hiển thị A/D% và Cấu trúc MA50%.
    """
    import streamlit as st

    snap = MarketSnapshot(ad_pct=ad_pct, above_ma50_pct=above_ma50_pct, momentum_score=momentum_score)
    rec = get_recommendation(snap)

    st.info(f"🟠 {rec['market_condition_label']}.")

    if rec["was_capped_by_breadth"]:
        st.warning(
            f"⚠️ Score tổng hợp gợi ý {rec['raw_allocation_pct']}% cổ phiếu, "
            f"nhưng đã bị GIỚI HẠN xuống tối đa {rec['ad_cap_pct']}% vì độ rộng thị trường "
            f"(A/D chỉ {ad_pct:.1f}%) đang yếu — ưu tiên an toàn vốn hơn Score kỹ thuật."
        )

    st.markdown("### 💡 Khuyến nghị hành động")
    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 Score", f"{rec['score']:+d}")
    col2.metric("📈 Tỷ trọng CP", f"{rec['stock_pct']}%")
    col3.metric("💵 Tiền mặt", f"{rec['cash_pct']}%")

    st.markdown(f"**{rec['action_label']}** — Cổ phiếu {rec['stock_pct']}% · Tiền mặt {rec['cash_pct']}%")
    st.progress(rec["stock_pct"] / 100)

    return rec
