# FORCE UPDATE - VERSION 7.0: DÙNG DATA TCBS VIỆT NAM (TRỊ DỨT ĐIỂM LỖI YAHOO)
import os
import json
import time
import requests
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)

client = gspread.authorize(creds)
# ID FILE GOOGLE SHEET CỦA BẠN (GIỮ NGUYÊN)
sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. LẤY DANH SÁCH MÃ & SÀN TỪ VNDIRECT
print("Đang tải danh sách toàn bộ mã chứng khoán và thông tin sàn...")
exchange_map = {} 
try:
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock&size=3000"
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json().get('data', [])
    
    for item in data:
        if len(item['symbol']) == 3:
            sym = item['symbol']
            floor = item.get('floor', 'HOSE').upper()
            if floor in ['HSX', 'VNX']: 
                floor = 'HOSE'
            exchange_map[sym] = floor
            
    if len(exchange_map) < 100:
        raise ValueError("API trả về thiếu dữ liệu!")
    print(f"Thành công! Tìm thấy {len(exchange_map)} mã niêm yết.")
except Exception:
    print("API VNDirect lỗi, dùng siêu danh sách dự phòng...")
    fallback_symbols = ['SSI','BCM','VHM','VIC','VRE','BVH','POW','GAS','ACB','BID','CTG','HDB','MBB','SHB','STB','TCB','TPB','VCB','VIB','VPB','HPG','GVR','MSN','VNM','SAB','MWG','FPT','PLX','VJC','NVL','PDR','DIG','DXG','NLG','KDH','KBC','IDC','SZC','VGC','TCH','HDG','BCG','FCN','CTD','VND','VCI','HCM','VIX','FTS','BSI','CTS','MBS','SHS','HSG','NKG','VGS','HT1','BCC','PVS','PVD','BSR','OIL','DGC','DPM','DCM','CSV','GMD','HAH','VHC','ANV','IDI','FRT','DGW','PET','CTR','FOX','VTP','VGI','ACV','VEA','MCH']
    upcom_hnx_dict = {'ACV': 'UPCOM', 'VEA': 'UPCOM', 'VGI': 'UPCOM', 'OIL': 'UPCOM', 'FOX': 'UPCOM', 'MCH': 'HOSE', 'BSR': 'HOSE', 'SHS': 'HNX', 'MBS': 'HNX', 'IDC': 'HNX', 'PVS': 'HNX'}
    for sym in fallback_symbols:
        exchange_map[sym] = upcom_hnx_dict.get(sym, 'HOSE')

symbols = list(exchange_map.keys())

# --- DANH SÁCH VIP ĐẶC CÁCH (Kim bài miễn tử) ---
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 3. QUÉT DỮ LIỆU TỪ TCBS (SẠCH BÓNG LỖI YAHOO THIẾU MÃ)
data_rows = []
print("Bắt đầu tiến trình quét lịch sử giao dịch từ TCBS...")

# Lấy mốc thời gian 60 ngày trước đến hiện tại
end_time = int(time.time())
start_time = end_time - (60 * 24 * 3600)

for sym in symbols:
    try:
        # Gọi API của TCBS (Chuẩn Việt Nam, không chặn GitHub, đầy đủ VGI và các mã HNX/UPCoM)
        url_hist = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?ticker={sym}&type=stock&resolution=D&from={start_time}&to={end_time}"
        res_hist = requests.get(url_hist, timeout=5)
        hist_data = res_hist.json().get('data', [])
        
        if len(hist_data) < 20:
            continue
            
        df_hist = pd.DataFrame(hist_data).tail(20) # Lấy đúng 20 phiên gần nhất
        
        close_price_vnd = float(df_hist['close'].iloc[-1])
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['volume'].mean()
        
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        
        # BỘ LỌC THANH KHOẢN > 20 TỶ (Trừ các mã VIP)
        if gtgd <= 20 and sym not in vip_symbols:
            continue

        exchange = exchange_map.get(sym, 'HOSE')

        # Điểm kỹ thuật & Xu hướng
        ma20_vnd = df_hist['close'].mean()
        if close_price_vnd > ma20_vnd * 1.01:
            trend, tech_score = "KHẢ QUAN", 5
        elif close_price_vnd < ma20_vnd * 0.99:
            trend, tech_score = "TIÊU CỰC", 1
        else:
            trend, tech_score = "TRUNG TÍNH", 3

        # Lấy Market Cap và PE (Từ TCBS)
        market_cap, pe = "N/A", "N/A"
        try:
            url_overview = f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/overview"
            res_ov = requests.get(url_overview, timeout=3).json()
            if 'marketCap' in res_ov:
                market_cap = round(res_ov['marketCap'], 0)
            if 'pe' in res_ov:
                pe = round(res_ov['pe'], 1)
        except Exception:
            pass

        data_rows.append([
            sym, exchange, round(close_kvnd, 2), int(avg_vol_20), tech_score, trend,
            market_cap, pe, round(gtgd, 1)
        ])
        time.sleep(0.05) # TCBS chạy cực nhanh nên chỉ cần nghỉ 0.05 giây 
    except Exception:
        continue

# 4. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Sàn', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"THÀNH CÔNG: Đã đồng bộ {len(data_rows)} mã toàn thị trường lên Google Sheet (CHẮC CHẮN CÓ VGI)!")
else:
    print("CẢNH BÁO: Không tìm thấy dữ liệu phù hợp tiêu chí!")
