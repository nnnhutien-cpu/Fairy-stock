import pandas as pd
import gspread
import time
import os
import json
from google.oauth2.service_account import Credentials # Thư viện mới, tạm biệt oauth2client
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"

def main():
    print("🚀 Bắt đầu cào dữ liệu: CHUẨN 5 CỘT - MỖI MÃ 1 DÒNG...")

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
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return

    try:
        df_companies = listing_companies()
        danh_sach_ma = df_companies['ticker'].tolist()
    except Exception:
        print("❌ Lỗi lấy danh sách mã")
        return

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    ket_qua = []

    # Quét 50 mã để test nhanh (Xóa chữ [:50] nếu muốn quét toàn thị trường)
    for ma in danh_sach_ma[:50]:
        try:
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            if df_hist is not None and not df_hist.empty and len(df_hist) >= 20:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # CHỈ LẤY ĐÚNG 1 DÒNG CUỐI CÙNG (HÔM NAY)
                dong_cuoi = df_hist.iloc[-1]
                
                # 1 & 2: Mã và Giá đóng cửa
                gia_goc = float(dong_cuoi['close'])
                gia_dong_cua = int(gia_goc * 1000 if gia_goc < 1000 else gia_goc)
                
                # 3 & 4: Khối lượng ngày và KLTB 20 ngày
                vol_ngay = int(dong_cuoi['volume'])
                vol_tb_20_ngay = int(df_hist['volume'].iloc[-20:].mean())
                
                # Tính điểm kỹ thuật để đánh giá xu hướng
                ma10 = float(df_hist['close'].iloc[-10:].mean()) * 1000 if df_hist['close'].iloc[-10:].mean() < 1000 else float(df_hist['close'].iloc[-10:].mean())
                ma20 = float(df_hist['close'].iloc[-20:].mean()) * 1000 if df_hist['close'].iloc[-20:].mean() < 1000 else float(df_hist['close'].iloc[-20:].mean())
                
                diem = 0
                if gia_dong_cua > ma10: diem += 1
                if gia_dong_cua > ma20: diem += 1
                if ma10 > ma20: diem += 1
                if vol_ngay > vol_tb_20_ngay: diem += 1
                
                # 5: Xu hướng ngắn hạn
                if diem == 4: xu_huong = "🔥 Rất Tích Cực"
                elif diem == 3: xu_huong = "🟢 Tích Cực"
                elif diem == 2: xu_huong = "🟡 Trung Lập"
                else: xu_huong = "🔴 Tiêu Cực"
                
                # Đóng gói chuẩn 5 cột
                ket_qua.append([ma, gia_dong_cua, vol_ngay, vol_tb_20_ngay, xu_huong])
                
            time.sleep(0.3)
        except Exception:
            continue

    # Đẩy lên Sheet
    if ket_qua:
        print(f"🚀 Đang đẩy {len(ket_qua)} dòng lên Sheet...")
        sheet.clear() 
        tieu_de = ["Mã", "Giá đóng cửa", "Khối lượng ngày", "Khối lượng trung bình 20 ngày", "Xu hướng ngắn hạn"]
        sheet.append_rows([tieu_de] + ket_qua)
        print("🎉 XONG! Bảng dữ liệu 5 cột đã hoàn thiện.")

if __name__ == "__main__":
    main()
