# --- PHẦN 1: THỐNG KÊ VN-INDEX (THANH KHOẢN REALTIME) ---
st.header("1. Thị Trường Chung (VN-INDEX)")

# Nhúng hàm lấy dữ liệu 5 phút (Nhớ thêm get_intraday_vnindex vào dòng import trên cùng)
from data_loader import get_stock_data, get_vnindex_data, get_all_tickers, get_intraday_vnindex

intraday_df = get_intraday_vnindex()

if intraday_df is not None and not intraday_df.empty:
    # 1. Xử lý thời gian
    intraday_df['time'] = pd.to_datetime(intraday_df['time'])
    intraday_df['date'] = intraday_df['time'].dt.date
    intraday_df['hour_min'] = intraday_df['time'].dt.strftime('%H:%M')
    
    dates = intraday_df['date'].unique()
    if len(dates) >= 2:
        today_date = dates[-1]
        yest_date = dates[-2]
        
        # 2. Tách dữ liệu Hôm nay và Hôm qua
        df_today = intraday_df[intraday_df['date'] == today_date].copy()
        df_yest = intraday_df[intraday_df['date'] == yest_date].copy()
        
        # 3. Tính khối lượng cộng dồn từ sáng đến giờ hiện tại
        df_today['Vol_Hôm_Nay'] = df_today['volume'].cumsum()
        df_yest['Vol_Hôm_Qua'] = df_yest['volume'].cumsum()
        
        # 4. Gộp bảng để vẽ biểu đồ
        chart_df = pd.merge(df_yest[['hour_min', 'Vol_Hôm_Qua']], 
                            df_today[['hour_min', 'Vol_Hôm_Nay']], 
                            on='hour_min', how='outer').sort_values('hour_min')
        chart_df.set_index('hour_min', inplace=True)
        
        # --- HIỂN THỊ GIAO DIỆN ---
        col1, col2 = st.columns([1, 2]) # Chia cột: Cột 1 nhỏ (Điểm số), Cột 2 to (Biểu đồ)
        
        with col1:
            # Lấy điểm số chốt phiên gần nhất từ bảng df_today
            if not df_today.empty:
                latest_point = df_today.iloc[-1]
                st.metric(label=f"VN-INDEX ({latest_point['hour_min']})", 
                          value=f"{latest_point['close']:.2f}")
                
                # Tính % thanh khoản so với CÙNG THỜI ĐIỂM hôm qua
                current_time = latest_point['hour_min']
                yest_vol_same_time = chart_df.loc[current_time, 'Vol_Hôm_Qua']
                today_vol_total = latest_point['Vol_Hôm_Nay']
                
                if pd.notna(yest_vol_same_time) and yest_vol_same_time > 0:
                    vol_diff_pct = ((today_vol_total - yest_vol_same_time) / yest_vol_same_time) * 100
                    st.metric(label="Tốc độ Thanh khoản", 
                              value=f"{int(today_vol_total):,}", 
                              delta=f"{vol_diff_pct:+.2f}% so với hôm qua")

        with col2:
            st.markdown("**📈 Biểu Đồ Thanh Khoản Cộng Dồn Trong Phiên**")
            st.line_chart(chart_df, color=["#FF0000", "#00FF00"]) # Đỏ: Hôm qua, Xanh: Hôm nay
else:
    st.warning("Đang kết nối dữ liệu VN-INDEX hoặc ngoài giờ giao dịch...")

st.divider()
