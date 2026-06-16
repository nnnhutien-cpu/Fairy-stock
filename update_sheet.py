import pandas as pd
import gspread
import time
import os
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
SPREADSHEET_KEY = "1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc"  # ID Google Sheet của bạn

def main():
    print("🚀 Bắt đầu cào dữ liệu và tính toán tín hiệu kỹ thuật...")

    # 1. Xác thực Google Sheet
    try:
        secret_key = os.environ.get("GCP_SA_KEY")
        if not secret_key:
            raise ValueError("Không tìm thấy biến GCP_SA_KEY trong hệ thống!")
        
        # Tạo file JSON ảo để đăng nhập
        with open("credentials.json", "w") as f:
            f.write(secret_key)
            
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
        print("✅ Kết nối Google Sheet thành công!")
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")
        return

    # 2. Lấy danh sách toàn bộ mã CK
    df_companies = listing_companies()
    if df_companies is None or df_companies.empty:
        print("❌ Lỗi: Không lấy được danh sách mã CK!")
        return
        
    danh_sach_ma = df_companies['ticker'].tolist()
    ket_qua = []
    
    # KÉO DỮ LIỆU 70 NGÀY (Để đảm bảo có đủ 40 phiên giao dịch thực tế trừ đi T7, CN)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=70)).strftime('%Y-%m-%d')

    print(f"🕵️ Đang xử lý {len(danh_sach_ma)} mã cổ phiếu...")

    # 3. Quét từng mã (Đang để test 50 mã đầu tiên, chạy thật bạn xóa chữ `[:50]` đi nhé)
    for ma in danh_sach_ma[:50]:
        try:
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            # Cần ít nhất 40 phiên để tính toán MA và Volume 2 đợt
            if df_hist is not None and len(df_hist) >= 40:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # --- LẤY GIÁ VÀ VOLUME GẦN NHẤT ---
                dong_cuoi = df_hist.iloc[-1]
                gia_hien_tai = dong_cuoi['close'] * 1000 if dong_cuoi['close'] < 1000 else dong_cuoi['close']
                vol_hien_tai = dong_cuoi['volume']
                
                # --- TÍNH TOÁN KHỐI LƯỢNG TRUNG BÌNH ---
                vol_20_ngay = df_hist['volume'].iloc[-20:].mean()          # 20 phiên gần nhất
                vol_20_phien_truoc = df_hist['volume'].iloc[-40:-20].mean() # 20 phiên của tháng trước đó
                
                # --- ĐÁNH GIÁ ĐIỂM KỸ THUẬT NGẮN HẠN (Thang điểm 0 - 4) ---
                # Mình dùng MA10 và MA20 để đánh giá sức mạnh xu hướng
                ma10 = df_hist['close'].iloc[-10:].mean() * 1000 if df_hist['close'].iloc[-10:].mean() < 1000 else df_hist['close'].iloc[-10:].mean()
                ma20 = df_hist['close'].iloc[-20:].mean() * 1000 if df_hist['close'].iloc[-20:].mean() < 1000 else df_hist['close'].iloc[-20:].mean()
                
                diem_kt = 0
                if gia_hien_tai > ma10: diem_kt += 1      # Giá vượt MA10
                if gia_hien_tai > ma20: diem_kt += 1      # Giá vượt MA20
                if ma10 > ma20: diem_kt += 1              # MA nhỏ cắt lên MA lớn
                if vol_hien_tai > vol_20_ngay: diem_kt += 1 # Volume nổ (vượt trung bình 20 ngày)
                
                # Xếp loại dựa trên điểm
                if diem_kt == 4:
                    xu_huong = "🔥 Rất Tích Cực"
                elif diem_kt == 3:
                    xu_huong = "🟢 Tích Cực"
                elif diem_kt == 2:
                    xu_huong = "🟡 Trung Lập"
                else:
                    xu_huong = "🔴 Tiêu Cực"
                
                # Đóng gói vào 1 dòng duy nhất cho mỗi mã
                ket_qua.append({
                    "Mã CK": ma,
                    "Ngày Cập Nhật": str(dong_cuoi['time']),
                    "Giá Hiện Tại": int(gia_hien_tai),
                    "Khối Lượng": int(vol_hien_tai),
                    "Vol TB 20 Ngày": int(vol_20_ngay),
                    "Vol TB 20 Phiên Trước": int(vol_20_phien_truoc),
                    "Điểm KT (0-4)": diem_kt,
                    "Xu Hướng Ngắn Hạn": xu_huong
                })
            
            # Ngủ 0.5s để API chứng khoán không khóa IP
            time.sleep(0.5) 
            
        except Exception as e:
            pass # Lỗi mã nào bỏ qua mã đó, chạy mã tiếp theo

    # 4. Ghi toàn bộ lên Sheet (ĐẢM BẢO KHÔNG TRÙNG LẶP)
    if ket_qua:
        df_output = pd.DataFrame(ket_qua)
        sheet.clear() # Tuyệt chiêu: Xóa sạch rác và dữ liệu cũ
        sheet.update([df_output.columns.values.tolist()] + df_output.values.tolist()) # Đổ bảng mới 100% vào
        print(f"✅ Đã cập nhật xong {len(df_output)} mã cổ phiếu lên Google Sheet!")
    else:
        print("⚠️ Bảng rỗng, không có dữ liệu để ghi.")

if __name__ == "__main__":
    main()
