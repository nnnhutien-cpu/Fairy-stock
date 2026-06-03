import requests

def get_stock_valuation(ticker, ichi_status):
    """
    Hàm cào dữ liệu trực tiếp từ API gốc (Không dùng vnstock để tránh lỗi phiên bản)
    Lấy chính xác Vốn hóa lưu hành và tính toán Đánh giá (Thấp/Cao/Trung bình)
    """
    try:
        # 1. Gọi trực tiếp API máy chủ gốc
        url = f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{ticker}/overview"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Lấy dữ liệu với thời gian chờ tối đa 5 giây
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            # 2. Trích xuất chính xác Vốn hóa, P/E, P/B
            market_cap = float(data.get('marketCap', 0.0))
            pe = float(data.get('pe', 0.0))
            pb = float(data.get('pb', 0.0))
            
            # 3. Logic Đánh giá Cổ phiếu (Định giá Thấp / Trung Bình / Cao)
            # Bạn có thể tự chỉnh sửa các con số 12, 1.5, 20... cho phù hợp với tiêu chuẩn của bạn
            if pe > 0 and pb > 0:
                if pe < 12 and pb < 1.5:
                    danh_gia = "🟢 Định giá thấp"
                elif pe > 20 or pb > 2.5:
                    danh_gia = "🔴 Định giá cao"
                else:
                    danh_gia = "🟡 Trung bình"
            else:
                danh_gia = "🟡 Trung bình"
                
            # Trả về đúng 2 cột cho file main.py và ui_layout.py
            return {
                "Vốn hóa lưu hành": market_cap,
                "Đánh Giá": danh_gia
            }
            
    except Exception as e:
        print(f"Lỗi khi cào {ticker}: {e}")
        pass
        
    # Nếu hệ thống mạng lỗi, trả về mặc định
    return {
        "Vốn hóa lưu hành": 0.0,
        "Đánh Giá": "N/A"
    }
