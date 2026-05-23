# FORCE UPDATE YFINANCE - VERSION 6.0: SÀN CHUẨN & VIP LIST ĐẶC CÁCH
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
# ID FILE GOOGLE SHEET CỦA BẠN
sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. LẤY DANH SÁCH MÃ & SÀN TỪ VNDIRECT
print("Đang tải danh sách toàn bộ mã chứng khoán và thông tin sàn...")
exchange_map = {} 
try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://dboard.vndirect.com.vn/'
    }
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock&size=3000"
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json().get('data', [])
    
    for item in data:
        if len(item['symbol']) == 3:
            sym = item['symbol']
            floor = item.get('floor', 'HOSE').upper()
            if floor == 'HSX' or floor == 'VNX': 
                floor = 'HOSE'
            exchange_map[sym] = floor
            
    if len(exchange_map) < 100:
        raise ValueError("API trả về thiếu dữ liệu!")
    print(f"Thành công! Tìm thấy {len(exchange_map)} mã niêm yết.")
    
except Exception as e:
    print("API VNDirect bị chặn, dùng siêu danh sách dự phòng...")
    fallback_symbols = [
        'SSI','BCM','VHM','VIC','VRE','BVH','POW','GAS','ACB','BID','CTG','HDB','MBB','SHB','STB','TCB','TPB','VCB','VIB','VPB','HPG','GVR','MSN','VNM','SAB','MWG','FPT','PLX','VJC','EIB','LPB','MSB','OCB','SSB','NAB','ABB','BVB','VBB',
        'NVL','PDR','DIG','DXG','NLG','KDH','KBC','IDC','SZC','VGC','TCH','HDG','BCG','FCN','CTD','HBC','CEO','IJC','ITA','SCR','HDC','L14','VCG','HHV','LCG','ASM','CII','CRE','DXS','KHG','NBB','NTL','QCG','VPH','EVF',
        'VND','VCI','HCM','VIX','FTS','BSI','CTS','MBS','SHS','AGR','BVS','ORS','VDS','TVS','APG','TVC','TVB','PSI','WSS',
        'HSG','NKG','VGS','HT1','BCC','PLC','KSB','DHA','SMC','TLH','POM','PAS','KMT','SHA','VNB',
        'PVS','PVD','BSR','OIL','PVT','CNG','NT2','GEG','REE','PC1','QTP','HND','SJD','VSH','TTA','HDW','LIG',
        'DGC','DPM','DCM','CSV','LAS','DDV','PHR','DPR','TRC','BFC','HNG',
        'GMD','HAH','VOS','VTO','VIP','PVP','TMS','SGP','C4G','G36','HUT',
        'VHC','ANV','IDI','FMC','CMX','DBC','BAF','PAN','HAG','SBT','TAR','LTG','MCH','SGC','HGX',
        'FRT','DGW','PET','HAX','CTR','FOX','VTP','MSR','KDC','DCL','NAF','PNJ','VGI','ACV','VEA','AMV','JVC','TNH'
    ]
    upcom_hnx_dict = {
        'ACV': 'UPCOM', 'VEA': 'UPCOM', 'VGI': 'UPCOM', 'OIL': 'UPCOM', 'ABB': 'UPCOM', 'BVB': 'UPCOM', 'NAB': 'UPCOM', 'FOX': 'UPCOM', 'VTP': 'HOSE', 'MCH': 'HOSE', 'BSR': 'HOSE',
        'SHS': 'HNX', 'MBS': 'HNX', 'IDC': 'HNX', 'PVS': 'HNX', 'CEO': 'HNX', 'HUT': 'HNX', 'L14': 'HNX', 'BVS': 'HNX'
    }
    for sym in fallback_symbols:
        exchange_map[sym] = upcom_hnx_dict.get(sym, 'HOSE')

symbols = list(exchange_map.keys())

# --- DANH SÁCH VIP ĐẶC CÁCH (Kim bài miễn tử bộ lọc GTGD) ---
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 3. QUÉT DỮ LIỆU BẰNG YFINANCE
data_rows = []
print("Bắt đầu tiến trình lọc thanh khoản > 20 tỷ và xử lý VIP...")

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
        
        # BỘ LỌC THANH KHOẢN: Loại mã < 20 tỷ NẾU KHÔNG NẰM TRONG DANH SÁCH VIP
        if gtgd <= 20 and sym not in vip_symbols:
            continue

        exchange = exchange_map.get(sym, 'HOSE')

        try:
            info = ticker.info
            market_cap_raw = info.get('marketCap', 0)
            market_cap = (market_cap_raw / 1000000000) if market_cap_raw else "N/A"
            pe = info.get('trailingPE', "N/A")
        except Exception:
            market_cap, pe = "N/A", "N/A"

        ma20 = df_hist['Close'].mean()
        if close_price_vnd > ma20 * 1.01:
            trend = "KHẢ QUAN"
            tech_score = 5
        elif close_price_vnd < ma20 * 0.99:
            trend = "TIÊU CỰC"
            tech_score = 1
        else:
            trend = "TRUNG TÍNH"
            tech_score = 3

        data_rows.append([
            sym, exchange, round(close_kvnd, 2), int(avg_vol_20), tech_score, trend,
            round(market_cap, 0) if isinstance(market_cap, float) else market_cap,
            round(pe, 1) if isinstance(pe, float) else pe, round(gtgd, 1)
        ])
        time.sleep(0.1)  
    except Exception:
        continue

# 4. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Sàn', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"THÀNH CÔNG: Đã đồng bộ {len(data_rows)} mã toàn thị trường lên Google Sheet (Bao gồm VGI)!")
else:
    print("CẢNH BÁO: Không tìm thấy dữ liệu phù hợp tiêu chí!")
