import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def render_ichimoku_simulation_chart(df):
    """
    [UX ĐỈNH CAO] Hàm vẽ biểu đồ kỹ thuật phân tầng chuyên nghiệp:
    - Khung trên (75% chiều cao): Biểu diễn Giá, Tenkan, Kijun và đổ màu Mây Kumo.
    - Khung dưới (25% chiều cao): Biểu diễn Volume dòng tiền (Nến xanh/đỏ theo phiên).
    """
    if df is None or df.empty:
        st.warning("⚠️ Không có dữ liệu để trực quan hóa biểu đồ.")
        return

    # Khởi tạo Subplots: 2 hàng, chung trục X (shared_xaxes=True) để khi cuộn chuột cả 2 tầng cùng chạy đều
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, 
                        row_width=[0.25, 0.75]) # Khối lượng 25%, Giá 75%

    # --- TẦNG 1: ĐƯỜNG GIÁ & MÂY ICHIMOKU ---
    # Biên mây Senkou A
    fig.add_trace(go.Scatter(x=df['time'], y=df['senkou_a'], 
                             line=dict(color='rgba(0,176,116,0.2)', width=1), 
                             name='Mây Kumo (Biên A)', showlegend=False), row=1, col=1)
    
    # Biên mây Senkou B + Đổ màu phần giao thoa (fill='tonexty') để tạo mây Kumo dạng mờ bóng ma
    fig.add_trace(go.Scatter(x=df['time'], y=df['senkou_b'], 
                             line=dict(color='rgba(214,39,40,0.2)', width=1), 
                             fill='tonexty', fillcolor='rgba(128,128,128,0.1)', 
                             name='Mây Kumo (Biên B)', showlegend=True), row=1, col=1)
    
    # Đường giá đóng cửa (Close Price)
    fig.add_trace(go.Scatter(x=df['time'], y=df['close'], 
                             line=dict(color='#1f77b4', width=2.5), 
                             name='Giá Đóng Cửa'), row=1, col=1)
    
    # Đường chuyển đổi Tenkan-sen
    fig.add_trace(go.Scatter(x=df['time'], y=df['tenkan'], 
                             line=dict(color='#ff7f0e', width=1.5, dash='solid'), 
                             name='Tenkan (Đường chuyển)'), row=1, col=1)
    
    # Đường chuẩn Kijun-sen
    fig.add_trace(go.Scatter(x=df['time'], y=df['kijun'], 
                             line=dict(color='#2ca02c', width=1.5, dash='solid'), 
                             name='Kijun (Đường chuẩn)'), row=1, col=1)

    # --- TẦNG 2: VOLUME DÒNG TIỀN (Thanh Bar Màu Tăng/Giảm) ---
    # Thuật toán tô màu cột volume: Nếu nến tăng (Close >= Open) màu xanh lá, ngược lại màu đỏ rực
    volume_colors = ['#00b074' if row['close'] >= row['open'] else '#d62728' for _, row in df.iterrows()]
    
    fig.add_trace(go.Bar(x=df['time'], y=df['volume'], 
                         marker_color=volume_colors, 
                         name='Volume (Dòng tiền 5P)'), row=2, col=1)

    # --- CẤU HÌNH GIAO DIỆN TINH TẾ (UX TỐI ƯU) ---
    fig.update_layout(
        height=600, # Chiều cao lý tưởng cho màn hình Dashboard rộng
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode='x unified', # Khi di chuột qua sẽ hiện thông số của tất cả các đường tại điểm đó cùng lúc
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), # Đẩy chú thích lên trên nằm ngang cho thoáng bảng
        template="plotly_white" # Nền trắng sạch sẽ theo phong cách hiện đại
    )
    
    # Định dạng tên trục Y cho từng tầng
    fig.update_yaxes(title_text="Mức Giá (VNĐ)", row=1, col=1)
    fig.update_yaxes(title_text="Khối Lượng", row=2, col=1)
    
    # Bắn Chart ra màn hình Streamlit dạng tự động co giãn theo khung container
    st.plotly_chart(fig, use_container_width=True)
