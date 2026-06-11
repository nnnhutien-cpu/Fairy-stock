import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def render_ichimoku_simulation_chart(df):
    """
    [UX ĐỈNH CAO] Hàm vẽ biểu đồ kỹ thuật phân tầng chuyên nghiệp:
    - Khung trên (75%): Nến Nhật, Mây Kumo, Kijun đỏ sẫm, Mắt Thần (Tín hiệu Mua/Bán).
    - Khung dưới (25%): Volume dòng tiền, Đường trung bình Volume MA20.
    - [TÍNH NĂNG MỚI]: Tự động Zoom hiển thị 6 tháng gần nhất trên nền dữ liệu 10 năm.
    """
    if df is None or df.empty:
        st.warning("⚠️ Không có dữ liệu để trực quan hóa biểu đồ.")
        return

    # Tính toán thêm đường MA20 cho Volume (nếu chưa có trong df)
    if 'vol_ma20' not in df.columns:
        df['vol_ma20'] = df['volume'].rolling(window=20).mean()

    # Khởi tạo Subplots: 2 hàng, chung trục X
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, 
                        row_width=[0.25, 0.75]) # Khối lượng 25%, Giá 75%

    # --- TẦNG 1: NẾN NHẬT & MÂY ICHIMOKU ---
    
    # 1. Vẽ nến Nhật (Candlestick) thay cho đường Line cơ bản
    fig.add_trace(go.Candlestick(x=df['time'],
                                 open=df['open'], high=df['high'],
                                 low=df['low'], close=df['close'],
                                 name='Nến Giá',
                                 increasing_line_color='#00b074', decreasing_line_color='#d62728'),
                  row=1, col=1)

    # 2. Biên mây Senkou A
    fig.add_trace(go.Scatter(x=df['time'], y=df['senkou_a'], 
                             line=dict(color='rgba(0,176,116,0.3)', width=1), 
                             name='Senkou A', showlegend=False), row=1, col=1)
    
    # 3. Biên mây Senkou B + Đổ màu phần giao thoa mây Kumo
    fig.add_trace(go.Scatter(x=df['time'], y=df['senkou_b'], 
                             line=dict(color='rgba(214,39,40,0.3)', width=1), 
                             fill='tonexty', fillcolor='rgba(128,128,128,0.15)', 
                             name='Mây Kumo', showlegend=True), row=1, col=1)
    
    # 4. Đường chuyển đổi Tenkan-sen (Màu cam)
    fig.add_trace(go.Scatter(x=df['time'], y=df['tenkan'], 
                             line=dict(color='#ff7f0e', width=1.5, dash='solid'), 
                             name='Tenkan (Đường chuyển)'), row=1, col=1)
    
    # 5. Đường chuẩn Kijun-sen (ĐỎ SẪM & IN ĐẬM theo yêu cầu)
    fig.add_trace(go.Scatter(x=df['time'], y=df['kijun'], 
                             line=dict(color='darkred', width=3, dash='solid'), 
                             name='Kijun (Đường chuẩn)'), row=1, col=1)

    # --- 💎 TÍNH NĂNG MẮT THẦN (TỰ ĐỘNG PHÁT HIỆN ĐIỂM GIAO CẮT) ---
    df_signal = df.copy()
    df_signal['prev_close'] = df_signal['close'].shift(1)
    df_signal['prev_kijun'] = df_signal['kijun'].shift(1)
    
    # MUA: Hôm qua nến đóng dưới Kijun, hôm nay cắt lên trên Kijun
    buy_pts = df_signal[(df_signal['prev_close'] <= df_signal['prev_kijun']) & (df_signal['close'] > df_signal['kijun'])]
    # BÁN: Hôm qua nến đóng trên Kijun, hôm nay cắt xuống dưới Kijun
    sell_pts = df_signal[(df_signal['prev_close'] >= df_signal['prev_kijun']) & (df_signal['close'] < df_signal['kijun'])]
    
    # Bắn mũi tên MUA (Xanh lá) dưới đáy nến
    fig.add_trace(go.Scatter(x=buy_pts['time'], y=buy_pts['low'] * 0.98,
                             mode='markers', marker=dict(symbol='triangle-up', size=14, color='#00b074', line=dict(width=1, color='darkgreen')),
                             name='Tín hiệu MUA'), row=1, col=1)
    
    # Bắn mũi tên BÁN (Đỏ sẫm) trên đỉnh nến
    fig.add_trace(go.Scatter(x=sell_pts['time'], y=sell_pts['high'] * 1.02,
                             mode='markers', marker=dict(symbol='triangle-down', size=14, color='#d62728', line=dict(width=1, color='darkred')),
                             name='Tín hiệu BÁN'), row=1, col=1)


    # --- TẦNG 2: VOLUME DÒNG TIỀN & ĐƯỜNG MA20 ---
    volume_colors = ['#00b074' if row['close'] >= row['open'] else '#d62728' for _, row in df.iterrows()]
    
    fig.add_trace(go.Bar(x=df['time'], y=df['volume'], 
                         marker_color=volume_colors, 
                         name='Volume'), row=2, col=1)
                         
    # Vẽ đè đường Volume MA20 uốn lượn màu cam
    fig.add_trace(go.Scatter(x=df['time'], y=df['vol_ma20'], 
                             line=dict(color='#FF6D00', width=2, shape='spline'), 
                             name='Volume MA20'), row=2, col=1)

    # --- 🚀 THUẬT TOÁN TỰ ĐỘNG ZOOM VÀO 6 THÁNG GẦN NHẤT ---
    # Tính toán mốc thời gian bắt đầu (lùi lại 150 nến) và mốc kết thúc (nến hiện tại)
    zoom_start = df['time'].iloc[-150] if len(df) > 150 else df['time'].iloc[0]
    zoom_end = df['time'].iloc[-1]
    # --------------------------------------------------------

    # --- CẤU HÌNH GIAO DIỆN TINH TẾ (UX TỐI ƯU) ---
    fig.update_layout(
        height=680, 
        margin=dict(l=10, r=10, t=20, b=10),
        hovermode='x unified', 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), 
        template="plotly_white",
        xaxis_rangeslider_visible=False, # Tắt dải kéo mặc định của nến Nhật để không bị vướng màn hình
        dragmode='pan', # Chuyển con trỏ chuột thành hình bàn tay để kéo trái/phải dễ dàng
        
        # 🔑 Kích hoạt vùng nhìn thấy giới hạn lúc khởi tạo biểu đồ
        xaxis=dict(range=[zoom_start, zoom_end])
    )
    
    # Loại bỏ khoảng trống dữ liệu vào Thứ 7, Chủ Nhật để nến đứng sát nhau (Giống TradingView)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    # Định dạng tên trục Y cho từng tầng
    fig.update_yaxes(title_text="Mức Giá (VNĐ)", row=1, col=1)
    fig.update_yaxes(title_text="Khối Lượng", row=2, col=1)
    
    # Bắn Chart ra màn hình Streamlit dạng tự động co giãn, KÈM BÙA CHÚ MỞ KHÓA LĂN CHUỘT
    st.plotly_chart(
        fig, 
        use_container_width=True, 
        config={
            'scrollZoom': True,           # Mở khóa lăn chuột để phóng to thu nhỏ
            'displayModeBar': True,       # Hiển thị thanh công cụ
            'modeBarButtonsToAdd': ['drawline', 'eraseshape'] # Thêm nút tự kẻ Trendline
        }
    )
