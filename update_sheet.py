import pandas as pd
import gspread
import time
import os
import json
import numpy as np
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data, ticker_overview
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
SPREADSHEET_KEY = "1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc"

def main():
    print("🚀 Bắt đầu cào dữ liệu chuẩn 10 Cột...")

    # 1. KẾT NỐI GOOGLE SHEET
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

    # 2. LẤY DANH SÁCH MÃ
    try:
        df_companies = listing_companies()
        danh_sach_ma = df_companies['ticker'].tolist()
    except Exception as e:
        print("❌ Lỗi lấy danh sách mã")
        return

    # Kéo 60 ngày để đủ dữ liệu tính RSI và MA20
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

    ket_qua = []
    print(f"🕵️ Bắt đầu quét dữ liệu... (1 Mã = 1 Dòng Duy Nhất)")

    # 3. QUÉT TỪNG MÃ (Đang để quét 50 mã đầu tiên để test, chạy thật hãy xóa chữ `[:50]` đi nhé)
    for ma in danh_sach_ma[:50]:
        try:
            # A. Cào Dữ Liệu Giá và Khối Lượng
            df_hist = stock_historical_data(ticker=ma, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
            
            if df_hist is not None and len(df_hist) >= 20:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # --- CHỐT CHẶN: CHỈ LẤY ĐÚNG 1 DÒNG GẦN NHẤT ---
                dong_cuoi = df_hist.iloc[-1]
                
                # 1. Đóng cửa (kVND)
                gia_goc = float(dong_cuoi['close'])
                gia_kvnd = round(gia_goc / 1000, 2) if gia_goc > 1000 else round(gia_goc, 2)
                
                # 2. KLTB 20N
                vol_hien_tai = int(dong_cuoi['volume'])
                kltb_20n = int(df_hist['volume'].iloc[-20:].mean())
                
                # 3. GTGD (tỷ đồng) = Giá (VND) * Vol / 1 tỷ
                gia_vnd = gia_kvnd * 1000
                gtgd_ty = round((gia_vnd * vol_hien_tai) / 1000000000, 2)
                
                # 4 & 5. Điểm KT & Xu hướng
                ma10 = df_hist['close'].iloc[-10:].mean()
                ma20 = df_hist['close'].iloc[-20:].mean()
                diem_kt = 0
                if gia_goc > ma10: diem_kt += 1
                if gia_goc > ma20: diem_kt += 1
                if ma10 > ma20: diem_kt += 1
                if vol_hien_tai > kltb_20n: diem_kt += 1
                
                if diem_kt == 4: xu_huong = "🔥 Rất Tích Cực"
                elif diem_kt == 3: xu_huong = "🟢 Tích Cực"
                elif diem_kt == 2: xu_huong = "🟡 Trung Lập"
                else: xu_huong = "🔴 Tiêu Cực"
                
                # 6. SMG ngắn hạn (Dùng RSI 14 phiên để chấm điểm Sức mạnh giá)
                delta = df_hist['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                smg = round(rsi.iloc[-1], 1) if not pd.isna(rsi.iloc[-1]) else 50
                
                # B. Cào Dữ Liệu Cơ Bản (P/E, P/BV, Vốn hóa)
                pe, pb, von_hoa = "N/A", "N/A", "N/A"
                try:
                    df_overview = ticker_overview(ma)
                    if not df_overview.empty:
                        info = df_overview.iloc[0]
                        # Vốn hóa (Tỷ đồng), P/E, P/BV
                        if 'marketCap' in info: von_hoa = round(float(info['marketCap']), 1)
                        if 'pe' in info: pe = round(float(info['pe']), 2)
                        if 'pb' in info: pb = round(float(info['pb']), 2)
                except Exception:
                    pass

                # --- ĐÓNG GÓI CHUẨN 10 CỘT YÊU CẦU ---
                ket_qua.append([
                    ma,                # Mã (đơn vị)
                    gia_kvnd,          # Đóng cửa (kvnd)
                    kltb_20n,          # KLTB 20N
                    diem_kt,           # Điểm kỹ thuật (*)
                    xu_huong,          # Xu hướng
                    smg,               # SMG ngắn hạn
                    von_hoa,           # Vốn hóa (tỷ đồng)
                    pe,                # P/E (lần)
                    pb,                # P/BV (lần)
                    gtgd_ty            # GTGD (tỷ đồng)
                ])
                
            time.sleep(0.3) # Nghỉ xíu tránh bị block API
        except Exception as e:
            continue

    # 4. GHI LÊN SHEET (Clear toàn bộ cũ, dán mới 100%)
    if ket_qua:
        print(f"🚀 Đang đẩy {len(ket_qua)} dòng lên Sheet...")
        sheet.clear()
        
        tieu_de = [
            "Mã (đơn vị)", "Đóng cửa (kvnd)", "KLTB 20N", "Điểm kỹ thuật (*)", 
            "Xu hướng", "SMG ngắn hạn", "Vốn hóa (tỷ đồng)", "P/E (lần)", 
            "P/BV (lần)", "GTGD (tỷ đồng)"
        ]
        
        sheet.append_rows([tieu_de] + ket_qua)
        print("🎉 XONG! Dữ liệu 10 Cột đã lên Google Sheet hoàn hảo.")
    else:
        print("⚠️ Không có dữ liệu để ghi.")

if __name__ == "__main__":
    main()
