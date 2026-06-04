import pandas as pd
import numpy as np
from vnstock import stock_historical_data
from datetime import datetime, timedelta

def get_5m_data(ticker, days_back=30):
    """
    Cào TRỰC TIẾP dữ liệu nến 5 phút từ API.
    Với nến 5 phút, bạn có thể lấy 30 ngày thoải mái mà không sợ API chặn.
    """
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    try:
        # [QUAN TRỌNG] Đổi resolution="5" để gọi thẳng nến 5 phút
        df_5m = stock_historical_data(symbol=ticker, 
                                      start_date=start_date, 
                                      end_date=end_date, 
                                      resolution="5", 
                                      type="stock")
        
        # Bẫy lỗi nếu không có dữ liệu
        if df_5m is None or df_5m.empty:
            return None
            
        # Xử lý chuẩn tên cột thời gian
        df_5m['time'] = pd.to_datetime(df_5m['time'])
        
        # Đảm bảo các cột giá trị là số thực (float) để tính Ichimoku không bị lỗi
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_5m.columns:
                df_5m[col] = pd.to_numeric(df_5m[col], errors='coerce')
        
        # Sắp xếp lại theo thời gian cho chắc chắn
        df_5m = df_5m.sort_values('time').reset_index(drop=True)
        
        # KHÔNG CẦN DÙNG LỆNH GỘP (RESAMPLE) NỮA! Trả về luôn!
        return df_5m
        
    except Exception as e:
        print(f"Lỗi cào dữ liệu 5 phút mã {ticker}: {e}")
        return None

# Đừng quên sửa lại tên hàm lúc gọi ở các phần sau của code nhé!
# Ví dụ: df = get_5m_data('SSI', days_back=30)
#        df = calculate_ichimoku_3m(df) # (Hàm tính Ichimoku cũ vẫn xài chung tốt vì nó chỉ tính toán dựa trên nến)
