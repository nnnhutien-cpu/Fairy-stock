import pandas as pd
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

# --- CẤU HÌNH HỆ THỐNG ---
SPREADSHEET_KEY = "1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc"  # ID Google Sheet của bạn
CREDENTIALS_FILE = "credentials.json"

def main():
    print("🚀 Bắt đầu cào dữ liệu THUẦN TÚY từ vnstock...")

    # 1. Mở cửa Google Sheet (Luôn ghi vào trang tính đầu tiên bên trái)
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).get_worksheet(0) 
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return

    # 2. Lấy danh sách mã chứng khoán
    df_companies = listing_companies()
    if df_companies is None or df_companies.empty:
        print("❌ Lỗi: Không lấy được danh sách mã CK!")
        return
        
    danh_sach_ma = df_companies['ticker'].tolist()
    ket_qua = []
    
    # Lùi 10 ngày để bao trọn cuối tuần, lễ tết
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    print(f"🕵️ Đang cào dữ liệu... (Hệ thống chạy chậm lại để chống block)")

    # 3. Lặp qua từng mã và cào (TẠM THỜI QUÉT 50 MÃ ĐỂ TEST CHO NHANH)
    for ma in danh_sach_ma[:50]:
        try:
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            if df_hist is not None and not df_hist.empty:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                dong_cuoi = df_hist.iloc[-1] # Lấy dòng cuối (ngày gần nhất)
                
                gia_dong_cua = dong_cuoi['close']
                if gia_dong_cua < 1000:
                    gia_dong_cua = gia_dong_cua * 1000
                
                ket_qua.append({
                    "Mã CK": ma,
                    "Ngày": str(dong_cuoi['time']),
                    "Giá Đóng Cửa": int(gia_dong_cua),
                    "Khối Lượng": int(dong_cuoi['volume'])
                })
            
            # Ngủ 0.5 giây để đánh lừa tường lửa của cty chứng khoán
            time.sleep(0.5) 
        except Exception:
            pass

    # 4. Ghi tất cả lên Sheet
    if ket_qua:
        df_output = pd.DataFrame(ket_qua)
        sheet.clear() # Xóa sạch rác cũ
        sheet.update([df_output.columns.values.tolist()] + df_output.values.tolist()) # Bơm số mới vào
        print(f"✅ Đã đổ thành công {len(df_output)} dòng dữ liệu lên Google Sheet!")
    else:
        print("⚠️ Bảng rỗng, không cào được dữ liệu nào.")

if __name__ == "__main__":
    main()
