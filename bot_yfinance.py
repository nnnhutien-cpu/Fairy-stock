# FORCE UPDATE YFINANCE - VERSION 4.0 QUÉT TOÀN THỊ TRƯỜNG 3 SÀN
import os
import json
import time
import requests
import pandas as pd
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)
sheet = client.open('Chứng khoán').sheet1

# 2. TỰ ĐỘNG LẤY DANH SÁCH ~1600 MÃ TỪ 3 SÀN (HOSE, HNX, UPCoM)
print("Đang lấy danh sách toàn bộ mã chứng khoán trên thị trường...")
try:
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock&size=3000"
    response = requests.get(url, headers=headers)
    data = response.json().get('data', [])
    # Lọc lấy các mã cổ phiếu hợp lệ (có đúng 3 chữ cái)
    symbols = [item['symbol'] for item in data if len(item['symbol']) == 3]
    print(f"Thành công! Tìm thấy {len(symbols)} mã chứng khoán đang niêm yết.")
except Exception as e:
    print("Lỗi khi lấy danh sách động, chuyển sang dùng danh sách dự phòng...")
    # Danh sách dự phòng 200 mã phổ biến phòng khi API bảo trì
    symbols = ['SSI','BCM','VHM','VIC','VRE','BVH','POW','GAS','ACB','BID','CTG','HDB','MBB','SHB','STB','TCB','TPB','VCB','VIB','VPB','HPG','GVR','MSN','VNM','SAB','MWG','FPT','PLX','VJC','EIB','LPB','MSB','OCB','SSB','NAB','ABB','BVB','VBB','NVL','PDR','DIG','DXG','NLG','KDH','KBC','IDC','SZC','VGC','TCH','HDG','BCG','FCN','CTD','HBC','CEO','IJC','ITA','SCR','HDC','L14','VCG','HHV','LCG','ASM','CII','CRE','DXS','KHG','NBB','NTL','QCG','VPH','EVF','VND','VCI','HCM','VIX','FTS','BSI','CTS','MBS','SHS','AGR','BVS','ORS','VDS','TVS','APG','TVC','TVB','PSI','WSS','HSG','NKG','VGS','HT1','BCC','PLC','KSB','DHA','SMC','TLH','POM','PAS','KMT','SHA','VNB','PVS','PVD','BSR','OIL','PVT','CNG','NT2','GEG','REE','PC1','QTP','HND','SJD','VSH','TTA','HDW','LIG','DGC','DPM','DCM','CSV','LAS','DDV','PHR','DPR','TRC','BFC','HNG','GMD','HAH','VOS','VTO','VIP','PVP','TMS','SGP','C4G','G36','HUT','VHC','ANV','IDI','FMC','CMX','DBC','BAF','PAN','HAG','SBT','TAR','LTG','MCH','SGC','HGX','FRT','DGW','PET','HAX','CTR','FOX','VTP','MSR','KDC','DCL','NAF','PNJ','VGI','ACV','VEA','AMV','JVC','TNH','AAA','APH','CKG','DAG','DLG','DRH','FIT','HQC','HTN','HUB','S99','SAM','SJF','SKG','TCD','TCL','TCM','TDM']

symbols = list(set(symbols)) # Loại bỏ các mã trùng lặp

# 3. QUÉT DỮ LIỆU BẰNG YFINANCE & LỌC > 20 TỶ
data_rows = []
print("Bắt đầu quét và lọc thanh khoản toàn thị trường...")

for sym in symbols:
    try:
        ticker = yf.Ticker(f"{sym}.VN")
        df_hist = ticker.history(period="2mo")
        # Bỏ qua nếu Yahoo Finance không có dữ liệu hoặc mã mới lên sàn chưa đủ 20 phiên
        if df_hist.empty or len(df_hist) < 20:
            continue

        df_hist = df_hist.tail(20)
        close_price_vnd = df_hist['Close'].iloc[-1]
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['Volume'].mean()

        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        
        # BỘ LỌC CHÍNH: Chỉ lấy mã > 20 Tỷ
        if gtgd <= 20:
            continue

        try:
            info = ticker.info
            market_cap_raw = info.get('marketCap', 0)
            market_cap = (market_cap_raw / 1000000000) if market_cap_raw else "N/A"
            pe = info.get('trailingPE', "N/A")
        except Exception:
            market_cap, pe = "N/A", "N/A"

        ma20 = df_hist['Close'].mean()
        trend = "KHẢ QUAN" if close_price_vnd > ma20 else "TRUNG TÍNH"
        tech_score = 5 if close_price_vnd > ma20 else 2

        data_rows.append([
            sym, round(close_kvnd, 2), int(avg_vol_20), tech_score, trend,
            round(market_cap, 0) if isinstance(market_cap, float) else market_cap,
            round(pe, 1) if isinstance(pe, float) else pe, round(gtgd, 1)
        ])
        
        # Giảm thời gian chờ xuống 0.1s để máy chủ quét 1600 mã nhanh hơn
        time.sleep(0.1)  
    except Exception:
        continue

# 4. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"THÀNH CÔNG: Đã đẩy {len(data_rows)} mã thỏa mãn điều kiện lên Sheet!")
else:
    print("CẢNH BÁO: Không có mã nào thỏa mãn điều kiện!")
