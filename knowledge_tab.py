"""
knowledge_tab.py
-----------------
Tab "📚 Kiến Thức" — nơi lưu trữ lý thuyết/cẩm nang tra cứu, tách riêng khỏi
logic tính toán tự động (logic tính toán nằm ở accumulation_signals.py và
được gắn vào tab "🕰️ Tích Lũy" đã có sẵn).

Cách dùng trong main.py:

    from knowledge_tab import render_knowledge_tab
    ...
    tab_market, tab_screener, ..., tab_knowledge = st.tabs([
        "🌟 Thị Trường", ..., "📚 Kiến Thức"
    ])
    ...
    with tab_knowledge:
        render_knowledge_tab()
"""

import streamlit as st


def render_knowledge_tab():
    st.subheader("📚 Cẩm Nang: Volume & Chu Kỳ Thị Trường")
    st.caption(
        "Tổng hợp lý thuyết dùng làm nền tảng cho các tín hiệu tự động ở tab "
        "'🕰️ Tích Lũy'. Đây là phần tra cứu tĩnh — không tính toán realtime."
    )
    st.divider()

    with st.expander("🌍 I. Chu kỳ vĩ mô & 3 trạng thái của thị trường", expanded=True):
        st.markdown("""
Thị trường tài chính vận động theo chu kỳ **Hưng thịnh → Suy thoái** lặp lại.
Khi nợ tăng dần và đòn bẩy được dùng thoải mái, bong bóng hình thành; khi mọi
người (kể cả người ít am hiểu tài chính) đều tham gia thị trường, đó thường
là dấu hiệu đỉnh chu kỳ.

Mọi cổ phiếu / chỉ số tại mọi thời điểm chỉ ở **một trong 3 trạng thái**:

1. **Xu hướng tăng**
2. **Trạng thái tích luỹ** (không có xu hướng rõ ràng)
3. **Xu hướng giảm**

Nguyên tắc quan trọng: phải xác định đúng trạng thái hiện tại trước, vì cách
đọc volume ở mỗi trạng thái là khác nhau — đọc sai trạng thái thì phân tích
volume trở nên vô nghĩa.
        """)

    with st.expander("📐 II. Xác định xu hướng bằng Ichimoku"):
        st.markdown("""
- Dùng đường trung bình **129 nến** (tuần): giá vượt xa trên 30% → vùng đỉnh,
  nhà đầu tư dài hạn có xu hướng chốt lời (đáy thì ngược lại).
- **Bắt đầu xu hướng tăng**: các thành phần Ichimoku (Tenkan, Kijun...) đều
  hướng lên và nằm trên mây (Kumo); MA65 & MA129 trên mây và hướng lên.
  Xu hướng giảm là ảnh gương của điều trên.
- **Kết thúc xu hướng** — 2 cách nhận biết, cho kết quả tương đương:
  - Chikou Span chui vào trong mây, hoặc
  - Giá chạm vào đường trung bình 129 nến.
        """)

    with st.expander("📊 III. Bài học về Volume (khối lượng / thanh khoản)"):
        st.markdown("""
**Nguyên tắc chân sóng lớn:** một con sóng lớn (đại sóng) chỉ hình thành khi
thanh khoản cao hơn bình thường xuất hiện kéo dài — nên theo dõi đồ thị Weekly/
Daily. Cụ thể: khối lượng gia tăng **1.5–2 lần khối lượng bình quân 20 nến**
là dấu hiệu chân sóng.

**Con dao 2 lưỡi:** volume tăng đột biến có thể là **đỉnh** hoặc **đáy** của
một con sóng — muốn phân biệt phải biết rõ thị trường đang ở loại đồ thị nào:

- **Loại 1 — có xu hướng** (tăng hoặc giảm — bản chất giống nhau, chỉ đảo ngược).
- **Loại 2 — không có xu hướng (tích luỹ).**

Mỗi loại dùng volume theo cách hoàn toàn khác nhau.
        """)

    with st.expander("🌱 IV. Giai đoạn TÍCH LUỸ (Accumulation)"):
        st.markdown("""
**Khi nào xảy ra tích luỹ?** Thường ngay sau một con sóng giảm mạnh, xoá sổ
phần lớn tài khoản nhà đầu tư nhỏ — tin xấu đã ra hết, không thể xấu thêm.

Đặc điểm nhận diện:
- Thị trường liên tục tạo đỉnh/đáy **thấp hơn** trước khi tạo đáy cuối cùng.
- Tin tức vĩ mô rất xấu, NĐT nhỏ hoảng loạn bán tháo bằng mọi giá.
- Đây là lúc dòng tiền lớn (BBs) bắt đầu **mua vào** nhờ lực bán tháo.

Trong quá trình tích luỹ, dòng tiền lớn mua ở vùng hỗ trợ rồi bán ở vùng
kháng cự để tiếp tục gom hàng giá rẻ, đồng thời "rũ bỏ" nhà đầu tư nhỏ lẻ
bám theo.

**Quy tắc volume trong tích luỹ:**
- Khối lượng **tăng** (khi giá đang ở vùng tích luỹ) → cân nhắc **bán bớt tối
  thiểu 50%** vì volume tăng lúc này thường là đỉnh của "sóng con".
- Khối lượng **giảm mạnh** (kiệt cung) → **vùng mua** phù hợp nhất; bán ở
  thời điểm khối lượng cao nhất.
- Cụ thể theo 3 dạng phá vùng hỗ trợ:
  - **Loại 1:** giá giảm qua hỗ trợ, Vol tăng mạnh, đóng cửa gần thấp nhất
    → tín hiệu **bán** (bán tốt nhất khi giá hồi lên kháng cự mà Vol < Vol
    lúc rũ bỏ).
  - **Loại 2:** giá giảm qua hỗ trợ, Vol tăng ít hơn Loại 1, sau đó hồi phục
    ≥ ½ spread trong ngày kèm Vol tăng cao hơn giai đoạn trước → tín hiệu
    **mua** (chỉ mua khi test thành công).
  - **Loại 3:** giá giảm nhẹ qua hỗ trợ kèm Vol/Spread suy kiệt → tín hiệu
    **mua**.
- Chỉ báo hỗ trợ tốt trong giai đoạn này: **RSI & MFI** — trên 70 là vùng
  bán, dưới 30 là vùng mua.

**Kết luận nhanh:** mua khi volume nằm **dưới MA20 khoảng 50%**; bán khi
volume **tăng mạnh vượt MA20 khoảng 30%**.
        """)

    with st.expander("📈 V. Xu hướng TĂNG & dấu hiệu PHÂN PHỐI (Distribution)"):
        st.markdown("""
Khi thị trường tăng giá, thanh khoản có xu hướng tăng do: doanh nghiệp làm ăn
tốt, margin nở ra, dòng tiền FOMO mới, và đòn bẩy công ty chứng khoán tăng.

**Điểm Phân phối** — thời điểm quan trọng nhất cần nhận biết: volume tăng
mạnh nhưng đây lại là **đỉnh**, báo hiệu giảm giá mạnh sắp tới. Dấu hiệu hội
tụ của cây Phân phối:

- Thị trường đang tăng, liên tục tạo đỉnh/đáy cao hơn.
- Tin tức toàn thị trường rất tích cực, tâm lý NĐT hưng phấn.
- NĐT nhỏ lao vào mua bằng mọi giá.
- Dòng tiền lớn (BBs) bắt đầu **bán ra**.
- Khối lượng tăng gấp ~2 lần MA20, giá vượt xa MA129 tuần khoảng 30%.
- Trước phân phối thường có **phân kỳ khối lượng**: volume giảm dần nhưng
  giá vẫn tăng — đặc biệt rõ ở cổ phiếu đầu cơ. Sau chuỗi phân kỳ dài, một
  cây volume tăng đột biến xuất hiện — cần đặt câu hỏi: cây này đang ở đỉnh
  hay đáy của xu hướng?

Phân phối thường diễn ra trong thời gian **ngắn hơn** nhiều so với tích luỹ.
        """)

    with st.expander("📉 VI. Dấu hiệu thị trường GIẢM GIÁ"):
        st.markdown("""
Sau một đại sóng tăng nóng kéo dài là giai đoạn giải chấp (margin call) hàng
loạt — các nhịp hồi trong giai đoạn này thường là "cú thoát hàng" chứ không
phải đảo chiều thật.

- Dòng tiền suy giảm kéo dài nhiều tuần trên đồ thị tuần → báo hiệu đợt giảm
  còn kéo dài.
- Muốn xác nhận **kết thúc** giảm giá: cần thấy dòng tiền tăng lên qua **nhiều
  phiên liên tiếp** — một cây nến tuần đơn lẻ chưa đủ để khẳng định.
- Bối cảnh vĩ mô đi kèm: lãi suất tăng để chống lạm phát, tỷ lệ thất nghiệp
  tăng theo để giảm cầu.
        """)

    with st.expander("🛡️ VII. Quản trị rủi ro"):
        st.markdown("""
- **Thị trường luôn luôn đúng** — luôn đặt stop-loss để bảo vệ NAV bằng mọi
  giá. Chỉ cần 1 lần sai trong 1000 lần đúng cũng có thể mất toàn bộ tài sản
  nếu không cắt lỗ.
- **Hạ giá vốn:** khi thị trường càng "nóng", nên chủ động hạ tỷ trọng cổ
  phiếu / hạ margin xuống.
        """)

    st.info(
        "💡 Các quy tắc volume ở mục IV và V phía trên đã được lập trình hoá "
        "thành tín hiệu tự động — xem tại tab **'🕰️ Tích Lũy'**."
    )
