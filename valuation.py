import pandas as pd
from vnstock import company_overview
import traceback

def get_stock_valuation(ticker, ichi_status):
    """
    Hàm cào dữ liệu Vốn hóa và Đánh giá (Đã được bọc lỗi an toàn)
    """
    try:
        # Gọi API lấy dữ liệu tổng quan
        df = company_overview(ticker)
        
        # Nếu DataFrame rỗng hoặc bị None
        if df is None or df.empty:
            return {"Vốn hóa lưu hành": 0.0, "Đánh Giá": str(ichi_status)}
            
        # Tìm cột chứa từ khóa "cap" (không phân biệt hoa thường)
        # Phiên bản cũ của vnstock có thể dùng 'marketCap', 'market_cap', hoặc tiếng Việt
        market_cap_col = None
        for col in df.columns:
            if 'cap' in str(col).lower() or 'vốn hóa' in str(col).lower():
                market_cap_col = col
                break
                
        # Trích xuất giá trị vốn hóa
        market_cap_val = 0.0
        if market_cap_col and market_cap_col in df.columns:
            try:
                # Ép kiểu an toàn
                market_cap_val = float(df[market_cap_col].iloc[0])
            except (ValueError, TypeError, IndexError):
                market_cap_val = 0.0
                
        return {
            "Vốn hóa lưu hành": market_cap_val,
            "Đánh Giá": str(ichi_status) # Ép kiểu chuỗi để tránh N/A
        }

    except Exception as e:
        # Trong trường hợp API sập hoàn toàn
        print(f"Lỗi khi cào {ticker}: {e}")
        return {
            "Vốn hóa lưu hành": 0.0, 
            "Đánh Giá": str(ichi_status) if ichi_status else "Lỗi API"
        }
