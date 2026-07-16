import pandas as pd
import numpy as np

def run_trend_engine(df, k17=17, k65=65, k129=129, hop_bich_threshold=0.0014):
    """
    Cỗ máy trạng thái (State Machine) mô phỏng xu hướng lịch sử.
    Quy tắc: Tăng -> Sideway -> Giảm -> Sideway. Không nhảy cóc.
    """
    df = df.copy()
    if df.empty or len(df) < k129:
        return df
        
    df.columns = [str(c).lower().strip() for c in df.columns]

    # 1. TÍNH TOÁN CÁC CHỈ BÁO NỀN TẢNG
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['kijun17'] = (df['high'].rolling(k17).max() + df['low'].rolling(k17).min()) / 2
    df['knife65'] = (df['high'].rolling(k65).max() + df['low'].rolling(k65).min()) / 2
    df['knife129'] = (df['high'].rolling(k129).max() + df['low'].rolling(k129).min()) / 2

    # Tính độ dốc (Up/Down) so với 5 phiên trước để lọc nhiễu
    df['kijun17_up'] = df['kijun17'] > df['kijun17'].shift(5)
    df['knife65_up'] = df['knife65'] > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    df['kijun17_down'] = df['kijun17'] < df['kijun17'].shift(5)
    df['knife65_down'] = df['knife65'] < df['knife65'].shift(5)
    df['knife129_down'] = df['knife129'] < df['knife129'].shift(5)

    # 2. KHỞI TẠO BIẾN CHO STATE MACHINE
    states = []
    hop_bich_flags = []
    chan_song_flags = []
    phan_phoi_flags = []
    
    current_state = "🟡 Sideway" # Trạng thái mặc định ban đầu
    
    # 3. CHẠY CỖ MÁY TRẠNG THÁI (Duyệt từng nến)
    for i in range(len(df)):
        if i < k129 + 5: # Bỏ qua các nến chưa đủ dữ liệu
            states.append("🟡 Sideway")
            hop_bich_flags.append(False)
            chan_song_flags.append(False)
            phan_phoi_flags.append(False)
            continue
            
        close = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        vol_ma20 = df['vol_ma20'].iloc[i]
        
        k17_val = df['kijun17'].iloc[i]
        k65_val = df['knife65'].iloc[i]
        k129_val = df['knife129'].iloc[i]
        
        k17_up = df['kijun17_up'].iloc[i]
        k65_up = df['knife65_up'].iloc[i]
        k129_up = df['knife129_up'].iloc[i]
        
        k17_down = df['kijun17_down'].iloc[i]
        k65_down = df['knife65_down'].iloc[i]
        k129_down = df['knife129_down'].iloc[i]

        # --- ĐIỀU KIỆN ĐỘNG HỌC ---
        # Tăng: 65 và 129 tạo mây dốc lên, giá & 17 nằm trên mây, tất cả cùng tiến
        is_uptrend_start = (k65_val > k129_val) and k65_up and k129_up and (k17_val > k65_val) and k17_up and (close > k65_val)
        
        # Giảm: 65 và 129 tạo mây dốc xuống, giá & 17 nằm dưới mây, tất cả cùng lùi
        is_downtrend_start = (k65_val < k129_val) and k65_down and k129_down and (k17_val < k65_val) and k17_down and (close < k65_val)

        # --- CHUYỂN TRẠNG THÁI (STATE TRANSITIONS) ---
        if current_state == "🟡 Sideway":
            if is_uptrend_start:
                current_state = "🟢 Tăng"
            elif is_downtrend_start:
                current_state = "🔴 Giảm"
                
        elif current_state == "🟢 Tăng":
            # Kết thúc Tăng -> Về Sideway: Giá cắt xuống Knife2(129)
            if close <= k129_val:
                current_state = "🟡 Sideway"
                
        elif current_state == "🔴 Giảm":
            # Kết thúc Giảm -> Về Sideway: Giá cắt lên Knife2(129)
            if close >= k129_val:
                current_state = "🟡 Sideway"

        states.append(current_state)

        # --- TÍN HIỆU & CỜ XÁC NHẬN (FLAGS) ---
        
        # 1. Hợp bích (Chỉ áp dụng khi chuẩn bị hoặc đang tăng)
        hop_bich = abs(k65_val - k129_val) / k129_val <= hop_bich_threshold
        hop_bich_flags.append(hop_bich)
        
        # 2. Chân sóng (Vol > 1.5x - 2x) & Vừa chuyển trạng thái sang Tăng
        is_chan_song = False
        if current_state == "🟢 Tăng" and states[i-1] != "🟢 Tăng":
            if vol >= 1.5 * vol_ma20 and close > k129_val * 1.02: # Vượt nhẹ mây
                is_chan_song = True
        chan_song_flags.append(is_chan_song)
        
        # 3. Phân phối / Tạo đỉnh (Chỉ khi đang trong Trend Tăng)
        is_phan_phoi = False
        if current_state == "🟢 Tăng":
            # Giá vượt xa 129 (>30%) và vol đột biến (kéo xả)
            gia_qua_xa = (close - k129_val) / k129_val >= 0.30
            if gia_qua_xa and vol >= 2.0 * vol_ma20:
                is_phan_phoi = True
            # Hoặc phân kỳ: Giá đang ở đỉnh nhưng Vol teo tóp (<0.7 MA20)
            elif close >= df['high'].rolling(20).max().iloc[i] * 0.95 and vol < 0.7 * vol_ma20:
                is_phan_phoi = True
        phan_phoi_flags.append(is_phan_phoi)

    # 4. GẮN KẾT QUẢ VÀO DATAFRAME
    df['State'] = states
    df['Flag_HopBich'] = hop_bich_flags
    df['Flag_ChanSong'] = chan_song_flags
    df['Flag_PhanPhoi'] = phan_phoi_flags
    
    return df
