import pandas as pd
import gspread
import time
import os
import json
import yfinance as yf
from google.oauth2.service_account import Credentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta

# ID Google Sheet của bạn
SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"

def get_data_vnstock(ticker, start_date, end_date):
    """Lớp 1: Lấy dữ liệu từ Vnstock"""
    try:
        df = stock_historical_data(ticker=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        if df is not None and not df.empty and len(df) >= 20:
            df.columns = [str(c).lower().strip() for c in df.columns]
            return df
    except Exception:
        pass
    return None

def get_data_yfinance(ticker):
    """Lớp 2: Lấy dữ liệu từ Yahoo Finance (Dự phòng khi Vnstock bị chặn IP)"""
    try:
        # Yahoo Finance dùng hậu tố .VN cho chứng khoán Việt Nam (VD: FPT.VN)
        stock = yf.Ticker(f"{ticker}.VN")
        df = stock.history(period="3mo")
        if not df.empty and len(df) >= 20:
            df = df.reset_index()
            df.columns = [str(c).lower().strip() for c in df.columns]
            return df
    except Exception:
        pass
    return None

def main():
    print("🚀 Khởi động Hệ thống Dữ liệu lõi kép (Vnstock + Yahoo Finance)...")

    # 1. Xác thực Google Sheet
    try:
        secret_key = os.environ.get("GCP_SA_KEY")
        if not secret_key:
            raise ValueError("Chưa cấu hình GCP_SA_KEY!")
        creds_dict = json.loads(secret_key)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
        print("✅ Kết nối Database Google Sheet thành công!")
    except Exception as e:
        print(f"❌ Lỗi xác thực: {e}")
        return

    # 2. Lấy danh sách mã & LOẠI BỎ CÁC CÔNG TY CHỨNG KHOÁN
    try:
        df_comp = listing_companies()
        if 'industry' in df_comp.columns:
            # Lọc bỏ các mã thuộc nhóm Dịch vụ tài chính / Chứng khoán
            df_comp = df_comp[~df_comp['industry'].str.contains('Chứng khoán|Financial Services', na=False, case=False)]
        
        danh_sach_ma = df_comp['ticker'].tolist()
        print(f"✅ Đã tải danh sách mã. Đã tự động loại bỏ các CTCK. Bắt đầu quét...")
    except Exception as e:
        print(f"❌ Lỗi lấy danh sách công ty: {e}")
        return

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    ket_qua = []

    # Quét 50 mã để test nhanh. Chạy thật bạn xóa chữ [:50] đi nhé.
    for ma in danh_sach_ma[:50]:
        # Kiến trúc Fallback: Thử Vnstock, nếu thất bại chuyển sang Yahoo
        df = get_data_vnstock(ma, start_date, end_date)
        nguon = "Vnstock"
        
        if df is None:
            df = get_data_yfinance(ma)
            nguon = "Yahoo"
            
        if df is None:
            print(f"⚠️ {ma}: Bị chặn ở cả 2 nguồn. Bỏ qua.")
            continue

        try:
            # Bốc đúng 1 dòng dữ liệu cuối cùng (Mới nhất)
            dong_cuoi = df.iloc[-1]
            
            vol_ngay = int(dong_cuoi['volume'])
            vol_tb_20 = int(df['volume'].iloc[-20:].mean())
            gia_dong_cua = float(dong_cuoi['close'])
            gia_hom_qua = float(df['close'].iloc[-2])
            ma20_gia = float(df['close'].iloc[-20:].mean())

            # 4. Đánh giá Xu hướng dựa trên Volume (Tín hiệu dòng tiền)
            if vol_ngay >= vol_tb_20 * 1.5:
                xu_huong_vol = "🔥 Bùng nổ khối lượng (Cầu cực mạnh)"
            elif vol_ngay > vol_tb_20:
                xu_huong_vol = "🟢 Tích cực (Cầu lớn hơn cung)"
            elif vol_ngay < vol_tb_20 * 0.5:
                xu_huong_vol = "🔴 Cạn kiệt thanh khoản"
            else:
                xu_huong_vol = "🟡 Đi ngang (Lưỡng lự)"

            # 5. Rating (Chấm điểm tổng hợp Dòng tiền + Giá)
            diem = 0
            if vol_ngay > vol_tb_20: diem += 1      # Điểm Volume
            if gia_dong_cua > ma20_gia: diem += 1   # Điểm Nền giá
            if gia_dong_cua > gia_hom_qua: diem += 1 # Điểm Xung lực

            if diem == 3: rating = "⭐ Hạng A (Rất mạnh)"
            elif diem == 2: rating = "⭐ Hạng B (Khá)"
            elif diem == 1: rating = "⭐ Hạng C (Yếu)"
            else: rating = "⭐ Hạng D (Rất yếu)"

            # Đóng gói 1 Hàng = 5 Cột
            ket_qua.append([ma, vol_ngay, vol_tb_20, xu_huong_vol, rating])
            print(f"🟢 {ma} ({nguon}) | Vol: {vol_ngay} | Rating: {rating}")
            
        except Exception as e:
            print(f"❌ Lỗi tính toán mã {ma}: {e}")
            
        time.sleep(0.3)

    # 3. Đẩy lên Google Sheet
    if ket_qua:
        print(f"🚀 Đang ghi {len(ket_qua)} dòng lên Sheet...")
        sheet.clear() 
        tieu_de = ["Mã CK", "Volume ngày", "Volume 20 ngày", "Xu hướng đánh giá trên volume", "Rating"]
        sheet.append_rows([tieu_de] + ket_qua)
        print("🎉 THÀNH CÔNG RỰC RỠ! Dữ liệu đã lên sàn.")
    else:
        print("⚠️ Toàn bộ dữ liệu trống. Hãy kiểm tra lại API.")

if __name__ == "__main__":
    main()
