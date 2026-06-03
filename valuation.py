import pandas as pd
from vnstock import company_overview

def get_stock_valuation(ticker, ichi_status):
    """
    Hàm cào dữ liệu Vốn hóa và Đánh giá
    """
    try:
        df = company_overview(ticker)
        if not df.empty:
            # 1. Trích xuất Vốn hóa (Thay vì P/E, P/B)
            market_cap = df['marketCap'].iloc[0]
            
            # (Bạn giữ nguyên logic đánh giá cũ của bạn ở đây nếu có)
            # Ví dụ: danh_gia = "Tích cực" nếu ichi_status == "Tốt" ...
            danh_gia = ichi_status # Hoặc bất kỳ logic nào bạn đang dùng
            
            # 2. BẮT BUỘC trả về Dictionary có chứa đúng key "Vốn hóa lưu hành"
            return {
                "Vốn hóa lưu hành": float(market_cap),
                "Đánh Giá": danh_gia
            }
    except Exception as e:
        pass
    
    # Trả về giá trị mặc định nếu API lỗi
    return {"Vốn hóa lưu hành": 0.0, "Đánh Giá": "N/A"}
