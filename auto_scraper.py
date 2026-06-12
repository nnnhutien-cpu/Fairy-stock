import requests
import pandas as pd
from datetime import datetime
import os
from supabase import create_client

# Lấy thông tin Supabase từ Biến môi trường (GitHub Secrets)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def scrape_and_update_reports():
    print("Bắt đầu cào dữ liệu báo cáo phân tích...")
    
    # 1. MÔ PHỎNG KẾT NỐI API TỔNG HỢP (VIETSTOCK/CAFEF)
    # Là kỹ sư, bạn có thể dùng F12 (Network tab) để lấy URL API Endpoint chính xác
    # Dưới đây là cấu trúc bóc tách dữ liệu chuẩn
    
    # Danh sách các CTCK mục tiêu
    target_brokers = ["VND", "SSI", "VCI", "MAS", "MBS", "KIS", "SSV", "KB", "VCBS", "CTS", "BSI"]
    
    # --- ĐOẠN NÀY LÀ LOGIC CÀO (BẠN ĐIỀN API THỰC TẾ) ---
    # headers = {'User-Agent': 'Mozilla/5.0...'}
    # payload = {'fromDate': '2026-01-01', 'toDate': datetime.now().strftime('%Y-%m-%d')}
    # response = requests.post('URL_API_CUA_TRANG_TONG_HOP', json=payload, headers=headers)
    # data = response.json()
    
    # TẠO DỮ LIỆU MẪU ĐỂ TEST PIPELINE (Mô phỏng kết quả trả về từ API)
    mock_data = [
        {"date": "2026-06-12", "ticker": "FPT", "company": "SSI", "action": "MUA", "buy_price": 135000, "target_price": 160000, "report_url": "https://static.vietstock.vn/FPT_SSI.pdf"},
        {"date": "2026-06-11", "ticker": "HPG", "company": "VCI", "action": "NẮM GIỮ", "buy_price": 31000, "target_price": 35000, "report_url": "https://static.vietstock.vn/HPG_VCI.pdf"},
        {"date": "2026-06-10", "ticker": "MBB", "company": "VND", "action": "MUA", "buy_price": 24000, "target_price": 29000, "report_url": "https://static.vietstock.vn/MBB_VND.pdf"}
    ]
    df = pd.DataFrame(mock_data)
    # ----------------------------------------------------
    
    # 2. LỌC ĐÚNG CÁC CTCK YÊU CẦU & CHUẨN HÓA DỮ LIỆU
    df = df[df['company'].isin(target_brokers)]
    
    if not df.empty:
        # Chuyển đổi thành List of Dictionaries để đẩy lên Supabase
        records = df.to_dict('records')
        
        # Lệnh UPSERT: Nếu trùng Ngày + Mã + CTCK thì bỏ qua hoặc cập nhật, không tạo dòng rác
        result = supabase.table("analyst_reports").upsert(records).execute()
        print(f"✅ Đã cập nhật thành công {len(records)} báo cáo vào Database!")
    else:
        print("Không có báo cáo mới nào trong ngày hôm nay.")

if __name__ == "__main__":
    scrape_and_update_reports()
