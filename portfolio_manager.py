"""
===============================================
📊 PORTFOLIO MANAGER - BẢNG QUẢN LÝ GIAO DỊCH
===============================================
Tác giả: Fairy Stock
Mô tả: Module quản lý danh mục 4 mã cổ phiếu với tỷ lệ phân bổ vốn
Tích hợp: Streamlit app "Cô Tiên Stock"

CÁCH SỬ DỤNG:
-------------
1. Copy file này vào thư mục project trên GitHub
2. Import vào app chính (app.py):
   from portfolio_manager import render_portfolio_dashboard
   
3. Thêm tab mới vào app.py:
   tab9 = st.tabs([... , "💼 QUẢN LÝ GIAO DỊCH"])
   with tab9:
       render_portfolio_dashboard()

TEST ĐỘC LẬP:
   streamlit run portfolio_manager.py

LỊCH SỬ PHIÊN BẢN:
------------------
v1.0 - 2026-08-04: Khởi tạo module với 4 mã, tỷ lệ 10-20-30-40%
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime


class PortfolioManager:
    """
    📈 Class quản lý danh mục đầu tư
    Hỗ trợ 4 mã cổ phiếu với chiến lược phân bổ vốn linh hoạt
    """
    
    def __init__(self):
        """Khởi tạo danh mục mặc định"""
        self._init_session_state()
    
    def _init_session_state(self):
        """Khởi tạo session state nếu chưa có"""
        if 'portfolio_config' not in st.session_state:
            st.session_state.portfolio_config = {
                'stocks': ['VN30-1', 'VN30-2', 'VN30-3', 'VN30-4'],
                'allocations': [10, 20, 30, 40],  # Tỷ lệ %
                'status': ['CHỜ', 'CHỜ', 'CHỜ', 'CHỜ'],  # MUA/GIỮ/BÁN/CHỜ
                'buy_prices': [0.0, 0.0, 0.0, 0.0],
                'current_prices': [0.0, 0.0, 0.0, 0.0],
                'quantities': [0, 0, 0, 0],
                'notes': ['', '', '', ''],
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        if 'total_capital' not in st.session_state:
            st.session_state.total_capital = 100_000_000  # 100 triệu VNĐ
        
        if 'trade_history' not in st.session_state:
            st.session_state.trade_history = []
    
    def update_stock(self, index, **kwargs):
        """Cập nhật thông tin một mã cổ phiếu"""
        for key, value in kwargs.items():
            if key in st.session_state.portfolio_config:
                st.session_state.portfolio_config[key][index] = value
        st.session_state.portfolio_config['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def calculate_profit_loss(self, index):
        """Tính lãi/lỗ cho một mã"""
        buy_price = st.session_state.portfolio_config['buy_prices'][index]
        current_price = st.session_state.portfolio_config['current_prices'][index]
        
        if buy_price > 0 and current_price > 0:
            pl_percent = ((current_price - buy_price) / buy_price) * 100
            return round(pl_percent, 2)
        return 0.0
    
    def get_portfolio_summary(self):
        """Tổng kết danh mục"""
        total_capital = st.session_state.total_capital
        invested = 0
        
        for i in range(4):
            qty = st.session_state.portfolio_config['quantities'][i]
            price = st.session_state.portfolio_config['current_prices'][i]
            invested += qty * price
        
        cash = total_capital - invested
        total_pl = sum([
            st.session_state.portfolio_config['quantities'][i] * 
            (st.session_state.portfolio_config['current_prices'][i] - 
             st.session_state.portfolio_config['buy_prices'][i])
            for i in range(4) if st.session_state.portfolio_config['buy_prices'][i] > 0
        ])
        
        return {
            'total_capital': total_capital,
            'invested': invested,
            'cash': cash,
            'total_pl': total_pl,
            'cash_ratio': (cash / total_capital * 100) if total_capital > 0 else 0
        }
    
    def suggest_trade(self, market_condition='TRUNG TÍNH'):
        """
        💡 Đề xuất giao dịch thông minh
        
        Args:
            market_condition: 'TỐT', 'TRUNG TÍNH', 'XẤU'
        
        Returns:
            list: Danh sách đề xuất giao dịch
        """
        suggestions = []
        
        # Quy tắc 1: Thị trường xấu → Bán hết
        if market_condition == 'XẤU':
            for i, stock in enumerate(st.session_state.portfolio_config['stocks']):
                status = st.session_state.portfolio_config['status'][i]
                if status in ['MUA', 'GIỮ']:
                    suggestions.append({
                        'type': 'SELL_ALL',
                        'stock': stock,
                        'reason': '🚨 Thị trường xấu - Nên bán hết và chờ',
                        'priority': 'CAO'
                    })
            return suggestions
        
        # Quy tắc 2: Cắt lỗ khi lỗ >5%
        for i, stock in enumerate(st.session_state.portfolio_config['stocks']):
            pl = self.calculate_profit_loss(i)
            if pl < -5:
                suggestions.append({
                    'type': 'CUT_LOSS',
                    'stock': stock,
                    'reason': f'⚠️ Đang lỗ {pl:.1f}% - Xem xét cắt lỗ',
                    'priority': 'CAO'
                })
        
        # Quy tắc 3: Chốt lời khi lãi >15%
        for i, stock in enumerate(st.session_state.portfolio_config['stocks']):
            pl = self.calculate_profit_loss(i)
            if pl > 15:
                suggestions.append({
                    'type': 'TAKE_PROFIT',
                    'stock': stock,
                    'reason': f'🎯 Đang lãi {pl:.1f}% - Có thể chốt lời 50%',
                    'priority': 'TRUNG BÌNH'
                })
        
        # Quy tắc 4: Thị trường tốt → Tăng tỷ lệ mã mạnh
        if market_condition == 'TỐT':
            best_stock = None
            best_pl = -999
            for i, stock in enumerate(st.session_state.portfolio_config['stocks']):
                pl = self.calculate_profit_loss(i)
                if pl > best_pl and pl > 0:
                    best_pl = pl
                    best_stock = stock
            
            if best_stock:
                suggestions.append({
                    'type': 'INCREASE',
                    'stock': best_stock,
                    'reason': f'📈 Mã mạnh nhất ({best_pl:.1f}%) - Có thể tăng tỷ lệ',
                    'priority': 'THẤP'
                })
        
        return suggestions


def render_portfolio_dashboard():
    """
    🎛️ Render toàn bộ dashboard quản lý danh mục
    Gọi hàm này trong tab của app chính
    """
    pm = PortfolioManager()
    
    # Header
    st.markdown("## 💼 BẢNG QUẢN LÝ GIAO DỊCH - 4 MÃ CỔ PHIẾU")
    st.markdown("*Chiến lược phân bổ vốn thông minh với quy tắc Mua/Bán/Chờ tự động*")
    st.markdown("---")
    
    # Cấu hình tổng quan
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.session_state.total_capital = st.number_input(
            "💰 Tổng Vốn Đầu Tư (VNĐ)",
            value=st.session_state.total_capital,
            step=1_000_000,
            format="%d"
        )
    
    with col2:
        market_condition = st.selectbox(
            "📊 Đánh Giá Thị Trường",
            ["TỐT", "TRUNG TÍNH", "XẤU"],
            help="Dựa vào xu hướng VN-Index và thanh khoản"
        )
    
    with col3:
        risk_level = st.selectbox(
            "⚠️ Mức Rủi Ro",
            ["Thấp", "Trung Bình", "Cao"]
        )
    
    st.markdown("---")
    
    # Bảng phân bổ vốn
    st.subheader("📋 Bảng Phân Bổ Vốn & Trạng Thái")
    
    # Tạo DataFrame hiển thị
    portfolio_data = []
    for i in range(4):
        config = st.session_state.portfolio_config
        stock = config['stocks'][i]
        alloc = config['allocations'][i]
        status = config['status'][i]
        buy_price = config['buy_prices'][i]
        current_price = config['current_prices'][i]
        qty = config['quantities'][i]
        pl = pm.calculate_profit_loss(i)
        capital = st.session_state.total_capital * (alloc / 100)
        
        portfolio_data.append({
            'Mã CP': stock,
            'Tỷ Lệ (%)': alloc,
            'Vốn Phân Bổ (VNĐ)': f"{capital:,.0f}",
            'Trạng Thái': status,
            'Giá Mua': f"{buy_price:,.2f}" if buy_price > 0 else '-',
            'Giá Hiện Tại': f"{current_price:,.2f}" if current_price > 0 else '-',
            'Số Lượng': qty if qty > 0 else '-',
            'Lãi/Lỗ (%)': f"{pl:+.2f}%" if buy_price > 0 and current_price > 0 else '-'
        })
    
    df = pd.DataFrame(portfolio_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Điều khiển chi tiết từng mã
    st.subheader("🎛️ Điều Khiển Chi Tiết Từng Mã")
    
    cols = st.columns(2)
    
    for i in range(4):
        with cols[i % 2]:
            config = st.session_state.portfolio_config
            stock = config['stocks'][i]
            
            with st.expander(f"🔍 {stock} ({config['allocations'][i]}%)", expanded=(i==0)):
                new_stock = st.text_input("Mã CP:", value=stock, key=f"stock_{i}")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    new_alloc = st.number_input(
                        "Tỷ lệ (%):",
                        value=float(config['allocations'][i]),
                        min_value=0.0, max_value=100.0, step=5.0,
                        key=f"alloc_{i}"
                    )
                with col_b:
                    new_status = st.selectbox(
                        "Trạng thái:",
                        ["CHỜ", "MUA", "GIỮ", "BÁN"],
                        index=["CHỜ", "MUA", "GIỮ", "BÁN"].index(config['status'][i]),
                        key=f"status_{i}"
                    )
                
                col_c, col_d = st.columns(2)
                with col_c:
                    new_buy = st.number_input(
                        "Giá mua:", value=float(config['buy_prices'][i]),
                        min_value=0.0, step=0.1, key=f"buy_{i}"
                    )
                with col_d:
                    new_current = st.number_input(
                        "Giá hiện tại:", value=float(config['current_prices'][i]),
                        min_value=0.0, step=0.1, key=f"current_{i}"
                    )
                
                new_qty = st.number_input(
                    "Số lượng (cổ phiếu):",
                    value=config['quantities'][i], min_value=0, step=100,
                    key=f"qty_{i}"
                )
                new_note = st.text_input("Ghi chú:", value=config['notes'][i], key=f"note_{i}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Lưu", key=f"save_{i}"):
                        pm.update_stock(
                            i,
                            stocks=new_stock,
                            allocations=int(new_alloc),
                            status=new_status,
                            buy_prices=new_buy,
                            current_prices=new_current,
                            quantities=new_qty,
                            notes=new_note
                        )
                        st.success(f"✅ Đã lưu {new_stock}")
                        st.rerun()
                
                with col_btn2:
                    if st.button("🔄 Reset", key=f"reset_{i}"):
                        pm.update_stock(
                            i,
                            status='CHỜ',
                            buy_prices=0.0,
                            current_prices=0.0,
                            quantities=0,
                            notes=''
                        )
                        st.info(f"🔄 Đã reset {new_stock}")
                        st.rerun()
    
    st.markdown("---")
    
    # Tổng kết danh mục
    st.subheader("📊 Tổng Kết Danh Mục")
    summary = pm.get_portfolio_summary()
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    with col_s1:
        st.metric("💵 Tổng Vốn",
                  f"{summary['total_capital'] / 1_000_000:.1f} Tr",
                  help="Tổng vốn đầu tư ban đầu")
    
    with col_s2:
        st.metric("📈 Đang Đầu Tư",
                  f"{summary['invested'] / 1_000_000:.1f} Tr",
                  f"{(summary['invested']/summary['total_capital']*100):.1f}%",
                  help="Số tiền đang nằm trong cổ phiếu")
    
    with col_s3:
        st.metric("💰 Tiền Mặt",
                  f"{summary['cash'] / 1_000_000:.1f} Tr",
                  f"{summary['cash_ratio']:.1f}%",
                  help="Tiền mặt sẵn sàng mua vào")
    
    with col_s4:
        st.metric("💎 Lãi/Lỗ Tổng",
                  f"{summary['total_pl'] / 1_000_000:.1f} Tr",
                  f"{(summary['total_pl']/summary['invested']*100):.1f}%" if summary['invested'] > 0 else "-",
                  help="Tổng lãi/lỗ chưa thực hiện")
    
    st.markdown("---")
    
    # 💡 Đề xuất giao dịch thông minh
    st.subheader("💡 Đề Xuất Giao Dịch Thông Minh")
    
    suggestions = pm.suggest_trade(market_condition)
    
    if suggestions:
        for s in suggestions:
            if s['priority'] == 'CAO':
                st.error(f"**{s['stock']}** - {s['reason']}")
            elif s['priority'] == 'TRUNG BÌNH':
                st.warning(f"**{s['stock']}** - {s['reason']}")
            else:
                st.info(f"**{s['stock']}** - {s['reason']}")
    else:
        if market_condition == 'TỐT':
            st.success("✅ Danh mục đang ổn định - Tiếp tục giữ và theo dõi")
        elif market_condition == 'TRUNG TÍNH':
            st.info("ℹ️ Thị trường trung tính - Quan sát thêm trước khi hành động")
    
    st.markdown("---")
    
    # Chiến lược giao dịch
    st.subheader("📖 Chiến Lược Giao Dịch")
    
    with st.expander("🔴 KHI NÀO BÁN?"):
        st.markdown("""
        **Quy tắc Bán:**
        - **Cắt lỗ:** Khi mã giảm >5% so với giá mua
        - **Bán khi xấu:** Tất cả 4 mã đều có tín hiệu kỹ thuật tiêu cực
        - **Bán toàn bộ:** VN-Index giảm >3% trong 1 phiên với thanh khoản thấp
        - **Chốt lời:** Khi lãi >15%, có thể bán 50% và giữ phần còn lại
        
        **Quy tắc "Bán mã này mua mã khác":**
        - Bán mã có tín hiệu xấu nhất trong danh mục
        - Dùng vốn đó mua mã có tín hiệu TÍCH CỰC mạnh nhất
        - Ưu tiên mã có momentum và thanh khoản cao
        """)
    
    with st.expander("🟢 KHI NÀO MUA?"):
        st.markdown("""
        **Quy tắc Mua:**
        - **Mua thăm dò:** 30% vốn phân bổ khi có tín hiệu tốt đầu tiên
        - **Mua thêm:** 70% còn lại khi xác nhận xu hướng tăng
        - **Mua khi thị trường tốt:** VN-Index trên MA20, thanh khoản tăng
        - **Mua đúng tỷ lệ:** Tuân thủ 10-20-30-40% phân bổ
        
        **Ưu tiên mã để mua:**
        - Mã có tín hiệu TÍCH CỰC từ bộ lọc kỹ thuật
        - Mã thuộc nhóm vốn hóa lớn, thanh khoản cao
        - Mã đang trong xu hướng tăng trung hạn
        """)
    
    with st.expander("⚪ KHI NÀO CHỜ (TIỀN MẶT)?"):
        st.markdown("""
        **Quy tắc Chờ:**
        - **Chờ khi xấu:** Thị trường giảm mạnh, tất cả mã đều xấu
        - **Chờ sau cắt lỗ:** Sau khi bán cắt lỗ, chờ tín hiệu mới
        - **Chờ khi không rõ ràng:** Không có mã nào nổi bật
        - **Chờ trước sự kiện:** Trước công bố KQKD, Fed họp...
        
        **Chiến thuật "Bán hết rồi chờ":**
        - Áp dụng khi thị trường PANIC (giảm >5%)
        - Giữ 100% tiền mặt trong 3-5 phiên
        - Chỉ quay lại khi có mã bứt phá với khối lượng lớn
        - Không bắt đáy, chờ xu hướng rõ ràng
        """)
    
    # Footer
    st.markdown("---")
    st.caption(f"🕐 Cập nhật lần cuối: {st.session_state.portfolio_config['last_updated']}")
    st.caption("💡 Tip: Cập nhật giá và trạng thái mỗi ngày để hệ thống đề xuất chính xác")


# ============================================
# TEST ĐỘC LẬP
# ============================================

if __name__ == "__main__":
    st.set_page_config(
        page_title="Portfolio Manager",
        page_icon="💼",
        layout="wide"
    )
    st.title("🧚‍♀️ Portfolio Manager - Test Mode")
    render_portfolio_dashboard()
