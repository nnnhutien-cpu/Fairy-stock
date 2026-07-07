import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from vnstock import stock_historical_data

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="Mô Phỏng Ichimoku", layout="wide", initial_sidebar_state="collapsed")

# --- 1. HÀM LẤY DỮ LIỆU TRỰC TIẾP (ĐÃ XÓA SUPABASE) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data_direct(ticker, days_back=500):
    """Lấy dữ liệu trực tiếp từ vnstock, bỏ qua Supabase"""
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        # Gọi trực tiếp vnstock
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df is not None and not df.empty:
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time')
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# --- 2. HÀM TÍNH TOÁN ICHIMOKU & VOLUME MA20 ---
def calculate_indicators(df):
    # Tính Tenkan & Kijun
    high_9 = df['high'].rolling(window=9).max()
    low_9 = df['low'].rolling(window=9).min()
    tenkan = (high_9 + low_9) / 2

    high_26 = df['high'].rolling(window=26).max()
    low_26 = df['low'].rolling(window=26).min()
    kijun = (high_26 + low_26) / 2

    # Tính Mây (Senkou Span A & B) dời về phía trước 26 phiên
    df['Senkou_A'] = ((tenkan + kijun) / 2).shift(26)
    
    high_52 = df['high'].rolling(window=52).max()
    low_52 = df['low'].rolling(window=52).min()
    df['Senkou_B'] = ((high_52 + low_52) / 2).shift(26)

    # Tính Volume MA20
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    
    return df

# --- 3. GIAO DIỆN TỐI GIẢN ---
st.title("🔮 Mô Phỏng Ichimoku & Volume")

# Khung nhập mã chứng khoán (Nhập xong nhấn Enter)
ticker_input = st.text_input("Nhập mã cổ phiếu (Gõ xong nhấn Enter):", value="HPG").upper().strip()

if ticker_input:
    with st.spinner(f"Đang tải dữ liệu {ticker_input}..."):
        df = get_stock_data_direct(ticker_input, days_back=500) # Lấy 500 ngày để đủ dữ liệu tính mây
        
        if df.empty:
            st.warning(f"⚠️ Không có dữ liệu cho mã {ticker_input}. Vui lòng kiểm tra lại.")
        else:
            df = calculate_indicators(df)
            
            # Cắt bớt phần dữ liệu rác (NaN) ở đầu để biểu đồ hiển thị đẹp hơn
            df_plot = df.tail(200).reset_index(drop=True)
            
            # --- VẼ BIỂU ĐỒ BẰNG PLOTLY ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, row_heights=[0.75, 0.25])

            # 1. Đường giá (Line Trắng)
            fig.add_trace(go.Scatter(x=df_plot['time'], y=df_plot['close'], 
                                     mode='lines', name='Giá Đóng Cửa', line=dict(color='white', width=2)), row=1, col=1)

            # 2. Mây Ichimoku Kumo
            fig.add_trace(go.Scatter(x=df_plot['time'], y=df_plot['Senkou_A'], 
                                     mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df_plot['time'], y=df_plot['Senkou_B'], 
                                     mode='lines', fill='tonexty', 
                                     fillcolor='rgba(139, 92, 246, 0.25)', # Đổ màu mây Tím
                                     line=dict(color='rgba(0,0,0,0)'), name='Mây Kumo'), row=1, col=1)

            # 3. Cột Khối lượng (Xanh/Đỏ)
            colors = ['#EF4444' if o > c else '#22C55E' for o, c in zip(df_plot['open'], df_plot['close'])]
            fig.add_trace(go.Bar(x=df_plot['time'], y=df_plot['volume'], 
                                 marker_color=colors, name='Khối lượng'), row=2, col=1)

            # 4. Đường Volume MA20 (Màu Vàng)
            fig.add_trace(go.Scatter(x=df_plot['time'], y=df_plot['Vol_MA20'], 
                                     mode='lines', name='Volume MA20', line=dict(color='#F59E0B', width=2)), row=2, col=1)

            # --- TÙY CHỈNH GIAO DIỆN DARK THEME TỐI GIẢN ---
            fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=10, r=10, t=10, b=10),
                height=650,
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            # Tắt thanh cuộn ở dưới để tập trung vào chart
            fig.update_xaxes(rangeslider_visible=False)
            
            st.plotly_chart(fig, use_container_width=True)
