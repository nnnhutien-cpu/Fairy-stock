import pandas as pd
from vnstock import company_overview

def get_stock_valuation(ticker, ichi_status):
    """
    Hàm cào dữ liệu Vốn hóa và Đánh giá
    """
    try:
        # Gọi hàm lấy tổng quan công ty
        df = company_overview(ticker)
        
        # Kiểm tra xem dữ liệu có trả về thành công không
        if df is not None and not df.empty:
            
            # Trích xuất Vốn hóa thị trường (marketCap)
            # Dùng .get() để tránh lỗi nếu API bất ngờ đổi tên cột
            market_cap_str = df.get('marketCap', [0]).iloc[0]
            
            # Đảm bảo chuyển đổi sang số thực (float)
            try:
                market_cap = float(market_cap_str)
            except (ValueError, TypeError):
                market_cap = 0.0
                
            danh_gia = ichi_status 
            
            # BẮT BUỘC TRẢ VỀ ĐÚNG 2 KEY NÀY (Tuyệt đối không trả về P/E, P/B nữa)
            return {
                "Vốn hóa lưu hành": market_cap,
                "Đánh Giá": danh_gia
            }
            
    except Exception as e:
        # Bỏ qua lỗi và trả về giá trị mặc định bên dưới
        pass
    
    # Trả về giá trị mặc định nếu API lỗi hoặc không có dữ liệu
    return {
        "Vốn hóa lưu hành": 0.0, 
        "Đánh Giá": "N/A"
    }
