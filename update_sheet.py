import pandas as pd
import gspread
import time
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
SPREADSHEET_KEY = "1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc"

def main():
    print("🚀 Bắt đầu cào dữ liệu và tính toán tín hiệu kỹ thuật...")

    # 1. Kết nối Google Sheet bằng Secret Key
    try:
        secret_key = os.environ.get("GCP_SA_KEY")
        if not secret_key:
            raise ValueError("Không tìm thấy chìa khóa GCP_SA_KEY!")
        
        creds_dict = json.loads(secret_key)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
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
    except Exception as e:
        print("❌ Không lấy được danh sách mã CK")
        return

    ket_qua = []
    
    # Lùi lại 70 ngày để đảm bảo luôn có đủ 40 phiên giao dịch thực tế
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=70)).strftime('%Y-%m-%d')

    print(f"🕵️ Đang xử lý tính toán cho các mã cổ phiếu...")

    # 3. Quét từng mã (Tạm quét 50 mã để test, ngon lành thì bạn xóa chữ [:50] đi nhé)
    for ma in danh_sach_ma[:50]:
        try:
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            if df_hist is not None and len(df_hist) >= 40:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # BÍ QUYẾT: CHỈ BỐC LẤY ĐÚNG 1 DÒNG CUỐI CÙNG (NGÀY GẦN NHẤT)
                dong_cuoi = df_hist.iloc[-1]
                
                gia_hien_tai = float(dong_cuoi['close'])
                if gia_hien_tai < 1000: gia_hien_tai *= 1000
                vol_hien_tai = int(dong_cuoi['volume'])
                
                # Tính Toán Trung Bình Khối Lượng
                vol_20_ngay = int(df_hist['volume'].iloc[-20:].mean())
                vol_20_phien_truoc = int(df_hist['volume'].iloc[-40:-20].mean())
                
                # Tính Toán MA (Trung bình giá)
                ma10 = float(df_hist['close'].iloc[-10:].mean())
                if ma10 < 1000: ma10 *= 1000
                ma20 = float(df_hist['close'].iloc[-20:].mean())
                if ma20 < 1000: ma20 *= 1000
                
                # Chấm điểm kỹ thuật (0-4 điểm)
                diem_kt = 0
                if gia_hien_tai > ma10: diem_kt += 1
                if gia_hien_tai > ma20: diem_kt += 1
                if ma10 > ma20: diem_kt += 1
                if vol_hien_tai > vol_20_ngay: diem_kt += 1
                
                # Xếp loại
                if diem_kt == 4: xu_huong = "🔥 Rất Tích Cực"
                elif diem_kt == 3: xu_huong = "🟢 Tích Cực"
                elif diem_kt == 2: xu_huong = "🟡 Trung Lập"
                else: xu_huong = "🔴 Tiêu Cực"
                
                ket_qua.append([
                    ma,
                    str(dong_cuoi['time']),
                    int(gia_hien_tai),
                    vol_hien_tai,
                    vol_20_ngay,
                    vol_20_phien_truoc,
                    diem_kt,
                    xu_huong
                ])
                
            time.sleep(0.3) # Nghỉ xíu tránh bị block
        except Exception as e:
            continue

    # 4. Ghi lên Sheet
    if ket_qua:
        print(f"🚀 Đang đẩy {len(ket_qua)} dòng lên Sheet...")
        sheet.clear() # TUYỆT CHIÊU: Xóa sạch rác cũ, bảng tính lúc nào cũng sạch sẽ 1 mã 1 dòng!
        
        tieu_de = ["Mã CK", "Ngày Cập Nhật", "Giá Hiện Tại", "Khối Lượng", "Vol TB 20 Ngày", "Vol TB 20 Phiên Trước", "Điểm KT", "Xu Hướng"]
        sheet.append_row(tieu_de)
        sheet.append_rows(ket_qua)
        print("🎉 XONG! Dữ liệu đã lên Google Sheet an toàn.")
    else:
        print("⚠️ Không có dữ liệu để ghi.")

if __name__ == "__main__":
    main()
