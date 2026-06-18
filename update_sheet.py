import pandas as pd
import gspread
import time
import os
import json
from google.oauth2.service_account import Credentials # ĐÃ VỨT BỎ OAUTH2CLIENT
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY" 

def main():
    print("🚀 Bắt đầu cào dữ liệu (Mỗi mã 1 dòng - 5 Cột Chuẩn)...")

    # 1. Kết nối Google Sheet bằng thư viện google-auth
    try:
        secret_key = os.environ.get("GCP_SA_KEY")
        if not secret_key:
            raise ValueError("Không tìm thấy chìa khóa GCP_SA_KEY!")
        
        creds_dict = json.loads(secret_key)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
        print("✅ Kết nối Google Sheet thành công!")
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")
        return

    # 2. Lấy danh sách mã chứng khoán toàn thị trường
    try:
        df_companies = listing_companies()
        danh_sach_ma = df_companies['ticker'].tolist()
    except Exception:
        print("❌ Lỗi lấy danh sách mã")
        return

    # Lấy lùi lại 60 ngày để có đủ dữ liệu tính Trung bình 20 ngày (MA20/Vol20)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    ket_qua = []

    print(f"🕵️ Bắt đầu quét dữ liệu...")

    # 3. THUẬT TOÁN CÀO DỮ LIỆU CHUẨN
    # (Tạm quét 50 mã để test nhanh, nếu chạy mượt bạn xóa chữ [:50] đi nhé)
    for ma in danh_sach_ma[:50]:
        try:
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            # Nếu có dữ liệu và đủ 20 phiên thì mới xử lý
            if df_hist is not None and not df_hist.empty and len(df_hist) >= 20:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # 🔥 CHỐT CHẶN: Chỉ lấy ĐÚNG 1 dòng dữ liệu của ngày gần nhất
                dong_cuoi = df_hist.iloc[-1]
                
                # Cột 2: Giá đóng cửa
                gia_goc = float(dong_cuoi['close'])
                gia_dong_cua = gia_goc * 1000 if gia_goc < 1000 else gia_goc
                
                # Cột 3 & 4: Volume Ngày và Volume TB 20 Ngày
                vol_ngay = int(dong_cuoi['volume'])
                vol_tb_20_ngay = int(df_hist['volume'].iloc[-20:].mean())
                
                # --- Tính điểm số kỹ thuật bên trong hệ thống ---
                ma10 = float(df_hist['close'].iloc[-10:].mean()) * 1000 if df_hist['close'].iloc[-10:].mean() < 1000 else float(df_hist['close'].iloc[-10:].mean())
                ma20 = float(df_hist['close'].iloc[-20:].mean()) * 1000 if df_hist['close'].iloc[-20:].mean() < 1000 else float(df_hist['close'].iloc[-20:].mean())
                
                diem_kt = 0
                if gia_dong_cua > ma10: diem_kt += 1
                if gia_dong_cua > ma20: diem_kt += 1
                if ma10 > ma20: diem_kt += 1
                if vol_ngay > vol_tb_20_ngay: diem_kt += 1
                
                # Cột 5: Đánh giá Xu Hướng
                if diem_kt == 4: xu_huong = "🔥 Rất Tích Cực"
                elif diem_kt == 3: xu_huong = "🟢 Tích Cực"
                elif diem_kt == 2: xu_huong = "🟡 Trung Lập"
                else: xu_huong = "🔴 Tiêu Cực"
                
                # Đóng gói đúng 5 cột bạn yêu cầu vào 1 hàng duy nhất
                ket_qua.append([
                    ma,                 # 1. Mã Chứng khoán
                    int(gia_dong_cua),  # 2. Giá đóng cửa
                    vol_ngay,           # 3. Volume ngày
                    vol_tb_20_ngay,     # 4. Volume trung bình 20 ngày
                    xu_huong            # 5. Đánh giá xu hướng
                ])
                
            time.sleep(0.3) # Nghỉ một chút để không bị block IP
        except Exception:
            # Lỗi mã nào thì bỏ qua, quét mã tiếp theo
            continue

    # 4. ĐẨY DỮ LIỆU LÊN GOOGLE SHEET
    if ket_qua:
        print(f"🚀 Đang đẩy {len(ket_qua)} dòng lên Sheet...")
        sheet.clear() # Quét sạch bảng cũ
        
        tieu_de = ["Mã Chứng khoán", "Giá Đóng Cửa", "Volume Ngày", "Volume Trung Bình 20 Ngày", "Đánh Giá Xu Hướng"]
        sheet.append_rows([tieu_de] + ket_qua) # Gắn bảng mới vào
        print("🎉 XONG! Dữ liệu đã lên chuẩn xác từng hàng.")
    else:
        print("⚠️ Không có dữ liệu để ghi.")

if __name__ == "__main__":
    main()
