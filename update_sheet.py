import pandas as pd
import gspread
import time
import os
import json
from google.oauth2.service_account import Credentials # TUYỆT CHIÊU: Thay thế hoàn toàn oauth2client
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
# Đã cập nhật đúng ID Google Sheet từ link mới của bạn
SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY" 

def main():
    print("🚀 Bắt đầu cào dữ liệu: 1 Mã = 1 Hàng, Bỏ giá mở cửa...")

    # 1. Kết nối Google Sheet bằng google-auth (Không dùng oauth2client nữa)
    try:
        secret_key = os.environ.get("GCP_SA_KEY")
        if not secret_key:
            raise ValueError("Không tìm thấy chìa khóa GCP_SA_KEY trong GitHub Secrets!")
        
        creds_dict = json.loads(secret_key)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # Sử dụng thư viện hiện đại có sẵn của bạn để đăng nhập
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
        print("✅ Kết nối Google Sheet thành công!")
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return

    # 2. Lấy danh sách mã
    try:
        df_companies = listing_companies()
        danh_sach_ma = df_companies['ticker'].tolist()
    except Exception:
        print("❌ Lỗi lấy danh sách mã từ vnstock")
        return

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    ket_qua = []

    print(f"🕵️ Bắt đầu quét dữ liệu kỹ thuật...")

    # 3. QUÉT TỪNG MÃ (Tạm quét 50 mã để test, ngon lành bạn xóa chữ [:50] đi nhé)
    for ma in danh_sach_ma[:50]:
        try:
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            if df_hist is not None and len(df_hist) >= 20:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # --- CHỐT CHẶN TUYỆT ĐỐI: CHỈ LẤY DUY NHẤT 1 DÒNG CUỐI (1 MÃ = 1 HÀNG) ---
                dong_cuoi = df_hist.iloc[-1]
                
                # 1. Giá đóng cửa (Đã bỏ hoàn toàn giá mở cửa)
                gia_goc = float(dong_cuoi['close'])
                gia_dong_cua = gia_goc * 1000 if gia_goc < 1000 else gia_goc
                
                # 2. Khối lượng trung bình 20 ngày
                vol_hien_tai = int(dong_cuoi['volume'])
                kltb_20n = int(df_hist['volume'].iloc[-20:].mean())
                
                # Tính toán các đường MA để chấm điểm
                ma10 = float(df_hist['close'].iloc[-10:].mean()) * 1000 if df_hist['close'].iloc[-10:].mean() < 1000 else float(df_hist['close'].iloc[-10:].mean())
                ma20 = float(df_hist['close'].iloc[-20:].mean()) * 1000 if df_hist['close'].iloc[-20:].mean() < 1000 else float(df_hist['close'].iloc[-20:].mean())
                
                # 3. Đánh giá điểm số (0 - 4)
                diem_kt = 0
                if gia_dong_cua > ma10: diem_kt += 1
                if gia_dong_cua > ma20: diem_kt += 1
                if ma10 > ma20: diem_kt += 1
                if vol_hien_tai > kltb_20n: diem_kt += 1
                
                # 4. Xu hướng hiện tại
                if diem_kt == 4: xu_huong = "🔥 Rất Tích Cực"
                elif diem_kt == 3: xu_huong = "🟢 Tích Cực"
                elif diem_kt == 2: xu_huong = "🟡 Trung Lập"
                else: xu_huong = "🔴 Tiêu Cực"
                
                # Đóng gói chuẩn 5 cột thông tin duy nhất
                ket_qua.append([
                    ma,                 # Mã CK
                    int(gia_dong_cua),  # Giá Đóng Cửa
                    kltb_20n,           # KLTB 20 Ngày
                    xu_huong,           # Xu Hướng Hiện Tại
                    diem_kt             # Đánh Giá Điểm Số
                ])
                
            time.sleep(0.3)
        except Exception:
            continue

    # 4. GHI LÊN SHEET (Clear sạch cũ, ghi mới đè lên)
    if ket_qua:
        print(f"🚀 Đang đẩy {len(ket_qua)} dòng lên Sheet...")
        sheet.clear() # Quét sạch rác và bảng cũ
        
        tieu_de = ["Mã CK", "Giá Đóng Cửa", "KLTB 20 Ngày", "Xu Hướng Hiện Tại", "Đánh Giá Điểm Số"]
        sheet.append_rows([tieu_de] + ket_qua)
        print("🎉 XONG! Dữ liệu đã lên chuẩn xác từng hàng.")
    else:
        print("⚠️ Không có dữ liệu để ghi.")

if __name__ == "__main__":
    main()
