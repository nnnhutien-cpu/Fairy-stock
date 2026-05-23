# FORCE UPDATE YFINANCE - VERSION 3.0 EXTENDED LIST
import os
import json
import time
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

# 2. DANH SÁCH MỞ RỘNG ~250 MÃ PHỔ BIẾN ĐỂ LỌC RA ~200 MÃ ĐẠT TIÊU CHUẨN
symbols = [
    # VN30 & Ngân hàng
    'SSI','BCM','VHM','VIC','VRE','BVH','POW','GAS','ACB','BID','CTG','HDB','MBB','SHB','STB','TCB','TPB','VCB','VIB','VPB','HPG','GVR','MSN','VNM','SAB','MWG','FPT','PLX','VJC','EIB','LPB','MSB','OCB','SSB','NAB','ABB','BVB','VBB',
    # Bất động sản, Xây dựng & Khu công nghiệp
    'NVL','PDR','DIG','DXG','NLG','KDH','KBC','IDC','SZC','VGC','TCH','HDG','BCG','FCN','CTD','HBC','CEO','IJC','ITA','SCR','HDC','L14','VCG','HHV','LCG','ASM','CII','CRE','DXS','KHG','NBB','NTL','QCG','VPH','EVF',
    # Chứng khoán
    'VND','VCI','HCM','VIX','FTS','BSI','CTS','MBS','SHS','AGR','BVS','ORS','VDS','TVS','APG','TVC','TVB','PSI','WSS',
    # Thép, Khai khoáng & Vật liệu xây dựng
    'HSG','NKG','VGS','HT1','BCC','PLC','KSB','DHA','SMC','TLH','POM','PAS','KMT','SHA','VNB',
    # Dầu khí, Năng lượng & Điện
    'PVS','PVD','BSR','OIL','PVT','CNG','NT2','GEG','REE','PC1','QTP','HND','SJD','VSH','TTA','HDW','LIG','BCG',
    # Hóa chất, Phân bón & Cao su
    'DGC','DPM','DCM','CSV','LAS','DDV','PHR','DPR','TRC','BFC','GVR','HNG',
    # Đầu tư công, Logistics & Cảng biển
    'GMD','HAH','VOS','VTO','VIP','PVP','TMS','SGP','C4G','G36','HUT','LCG','FCN',
    # Thủy sản, Nông nghiệp & Thực phẩm
    'VHC','ANV','IDI','FMC','CMX','DBC','BAF','PAN','HAG','SBT','TAR','LTG','MCH','VNM','SGC','HGX',
    # Công nghệ, Bán lẻ, Y tế & Viễn thông
    'FRT','DGW','PET','HAX','CTR','FOX','VTP','MSR','KDC','DCL','NAF','PNJ','VGI','ACV','VEA','AMV','JVC','TNH',
    # Các mã Midcap tích cực bổ sung khác
    'AAA','APH','CKG','DAG','DLG','DRH','FIT','HQC','HTN','HUB','S99','SAM','SJF','SKG','TCD','TCL','TCM','TDM'
]

# Loại bỏ trùng lặp nếu có để tối ưu hóa thời gian chạy
symbols = list(set(symbols))

data_rows = []
for sym in symbols:
    try:
        ticker = yf.Ticker(f"{sym}.VN")
        df_hist = ticker.history(period="2mo")
        if df_hist.empty or len(df_hist) < 20:
            continue

        df_hist = df_hist.tail(20)
        close_price_vnd = df_hist['Close'].iloc[-1]
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['Volume'].mean()

        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        
        # BỘ LỌC THANH KHOẢN: Có thể hạ xuống 10 hoặc 15 nếu muốn lấy nhiều mã hơn nữa
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
            sym,
            round(close_kvnd, 2),
            int(avg_vol_20),
            tech_score,
            trend,
            round(market_cap, 0) if isinstance(market_cap, float) else market_cap,
            round(pe, 1) if isinstance(pe, float) else pe,
            round(gtgd, 1)
        ])
        time.sleep(0.4)  # Đảm bảo tốc độ quét an toàn cho lượng mã lớn
    except Exception:
        continue

# 3. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("THÀNH CÔNG: Đã cập nhật danh sách mở rộng lên Google Sheet!")
else:
    print("CẢNH BÁO: Không có dữ liệu nào thỏa mãn bộ lọc!")
