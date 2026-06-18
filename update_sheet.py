import pandas as pd
import gspread
import time
import os
import json
from google.oauth2.service_account import Credentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"

def main():
    print("🚀 Bắt đầu dò tìm nguyên nhân mất dữ liệu...")

    try:
        secret_key = os.environ.get("GCP_SA_KEY")
        if not secret_key:
            raise ValueError("Không tìm thấy GCP_SA_KEY!")
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
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách mã: {e}")
        return

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    ket_qua = []

    print(f"🕵️ BẮT ĐẦU QUÉT VÀ HIỆN LỖI CHI TIẾT...")

    # Quét thử 10 mã để xem lỗi là gì cho nhanh
    for ma in danh_sach_ma[:10]:
        try:
            print(f"\n--- Đang xử lý mã: {ma} ---")
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            # KIỂM TRA XEM BỊ CHẶN HAY KHÔNG
            if df_hist is None:
                print(f"⚠️ {ma}: vnstock trả về None (Không có dữ liệu).")
                continue
            if df_hist.empty:
                print(f"⚠️ {ma}: vnstock trả về bảng rỗng (Bị chặn IP hoặc API lỗi).")
                continue
            if len(df_hist) < 20:
                print(f"⚠️ {ma}: Có dữ liệu nhưng chỉ có {len(df_hist)} dòng, không đủ 20 phiên.")
                continue
                
            df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
            print(f"✅ {ma}: Lấy thành công {len(df_hist)} ngày! Các cột hiện có: {list(df_hist.columns)}")
            
            dong_cuoi = df_hist.iloc[-1]
            gia_goc = float(dong_cuoi['close'])
            gia_dong_cua = int(gia_goc * 1000 if gia_goc < 1000 else gia_goc)
            
            vol_ngay = int(dong_cuoi['volume'])
            vol_tb_20_ngay = int(df_hist['volume'].iloc[-20:].mean())
            
            ma10 = float(df_hist['close'].iloc[-10:].mean()) * 1000 if df_hist['close'].iloc[-10:].mean() < 1000 else float(df_hist['close'].iloc[-10:].mean())
            ma20 = float(df_hist['close'].iloc[-20:].mean()) * 1000 if df_hist['close'].iloc[-20:].mean() < 1000 else float(df_hist['close'].iloc[-20:].mean())
            
            diem = 0
            if gia_dong_cua > ma10: diem += 1
            if gia_dong_cua > ma20: diem += 1
            if ma10 > ma20: diem += 1
            if vol_ngay > vol_tb_20_ngay: diem += 1
            
            if diem == 4: xu_huong = "🔥 Rất Tích Cực"
            elif diem == 3: xu_huong = "🟢 Tích Cực"
            elif diem == 2: xu_huong = "🟡 Trung Lập"
            else: xu_huong = "🔴 Tiêu Cực"
            
            ket_qua.append([ma, gia_dong_cua, vol_ngay, vol_tb_20_ngay, xu_huong])
            print(f"🟢 {ma}: Đã tính toán xong và đóng gói!")
            
        except Exception as e:
            # IN THẲNG LỖI RA MÀN HÌNH NẾU SAI TÊN CỘT
            print(f"❌ {ma} LỖI TÍNH TOÁN NGẦM: {e}")
            
        time.sleep(1)

    if ket_qua:
        print(f"\n🚀 Đang đẩy {len(ket_qua)} dòng lên Sheet...")
        sheet.clear() 
        tieu_de = ["Mã CK", "Giá đóng cửa", "Khối lượng ngày", "Khối lượng trung bình 20 ngày", "Xu hướng ngắn hạn"]
        sheet.append_rows([tieu_de] + ket_qua)
        print("🎉 XONG! Đã có dữ liệu lên Sheet.")
    else:
        print("\n⚠️ TOÀN BỘ ĐỀU THẤT BẠI. HÃY ĐỌC LOG Ở TRÊN ĐỂ XEM LỖI GÌ!")

if __name__ == "__main__":
    main()
