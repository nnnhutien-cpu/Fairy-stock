# FORCE UPDATE - VERSION 11.0: THE ULTIMATE VNSTOCK (VƯỢT TƯỜNG LỬA, FULL 3 SÀN)
import os
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from vnstock import stock_historical_data, ticker_overview

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

# 2. HÀM TÍNH TOÁN RSI
def compute_rsi(series, window=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# 3. SIÊU CƠ SỞ DỮ LIỆU OFFLINE 350+ MÃ (Không gọi API lấy danh sách để chống chặn)
print("Đang nạp Siêu danh sách mã chứng khoán 3 sàn...")

hose_symbols = ['SSI','VHM','VIC','HPG','VNM','VCB','BID','CTG','TCB','VPB','MBB','STB','ACB','SHB','VIB','HDB','LPB','TPB','MSB','OCB','SSB','EIB','NAB','NVL','PDR','DIG','DXG','NLG','KDH','KBC','VGC','SZC','HDG','BCG','FCN','CTD','VND','VCI','HCM','VIX','FTS','BSI','CTS','AGR','ORS','VDS','TVS','HSG','NKG','SMC','TLH','DGC','DPM','DCM','CSV','PHR','GVR','DPR','TRC','GMD','HAH','VOS','VHC','ANV','IDI','FMC','DBC','BAF','HAG','PAN','SBT','FRT','DGW','PET','MWG','PNJ','MSN','SAB','VJC','HVN','FPT','PLX','GAS','POW','NT2','GEG','REE','PC1','ASM','CII','HBC','VCG','HHV','LCG','HDC','IJC','SCR','CRE','KHG','DXS','PTB','GIL','TCM','TNG','VSH','SJD','SBA','TDM','BWE','VPD','VPI','QCG','TCH','HHS','HAX','CMX','DAT','EVF','FIT','HQC','ITA','OGC','HNG','TTF','AAA','APH','NHH','BMP','NTP','DRC','CSM','SRC','VTO','VIP','PVT']
hnx_symbols = ['SHS','MBS','IDC','PVS','CEO','HUT','L14','BVS','VGS','TIG','TAR','THD','BAB','NVB','PVC','PVB','APS','IDJ','API','AAV','AMV','VC3','VC7','MST','CSC','DDG','DTD','MCO','MBG','NTH','SDA','LIG','TTH','VIG','HDA','SCI','SRA','TVC','GKM']
upcom_symbols = ['BSR','ACV','VEA','MCH','VGI','FOX','VTP','OIL','ABB','BVB','VBB','SGB','PGB','KLB','SBS','AAS','VFS','C4G','G36','DDV','PAS','QNS','LTG','MSR','HTM','VGT','VNZ','SGP','PHP','TCI','DSC','BOT','DRI','TDS','HND','QTP','UPC','XDC','HSV']

exchange_map = {}
for s in hose_symbols: exchange_map[s] = 'HOSE'
for s in hnx_symbols: exchange_map[s] = 'HNX'
for s in upcom_symbols: exchange_map[s] = 'UPCOM'

symbols = list(exchange_map.keys())

# KIM BÀI MIỄN TỬ (Luôn giữ lại dù thanh khoản sụt giảm)
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 4. QUÉT DỮ LIỆU BẰNG VNSTOCK (Bao trọn 3 sàn)
data_rows = []
print(f"Bắt đầu quét {len(symbols)} mã bằng VNSTOCK...")

# Lấy dữ liệu 90 ngày qua để tính RSI và MA20 cho chuẩn
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

for sym in symbols:
    try:
        exchange = exchange_map.get(sym, 'HOSE')
        
        # Dùng VNSTOCK cào lịch sử giá (Thư viện tự lách tường lửa)
        df = stock_historical_data(symbol=sym, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df is None or df.empty or len(df) < 30:
            continue
            
        # Tính RSI
        df['RSI'] = compute_rsi(df['close'], 14)
        
        # Lấy 20 phiên gần nhất
        df = df.tail(20)
        
        close_price = float(df['close'].iloc[-1]) # Giá vnstock đã chia sẵn (ví dụ 25.5 = 25,500 đ)
        avg_vol_20 = float(df['volume'].mean())
        last_vol = float(df['volume'].iloc[-1])
        
        # Tính GTGD (Giá vnstock đang ở đơn vị nghìn đồng)
        gtgd = (close_price * 1000 * avg_vol_20) / 1000000000
        rsi_current = float(df['RSI'].iloc[-1])
        
        # LỌC THANH KHOẢN > 20 TỶ 
        if gtgd <= 20 and sym not in vip_symbols:
            continue

        ma20 = float(df['close'].mean())
        
        # HỆ THỐNG CHẤM ĐIỂM AI (0-100)
        score = 0
        if close_price > ma20 * 1.02: score += 40
        elif close_price > ma20: score += 25
        else: score += 10
        
        if 50 <= rsi_current <= 65: score += 30 
        elif 65 < rsi_current <= 75: score += 20 
        elif 40 <= rsi_current < 50: score += 15 
        else: score += 5 

        if last_vol > avg_vol_20 * 1.5: score += 30 
        elif last_vol > avg_vol_20 * 1.1: score += 20
        else: score += 10

        if score >= 75: trend = "TÍCH CỰC"
        elif score >= 50: trend = "TRUNG TÍNH"
        else: trend = "TIÊU CỰC"

        # Dùng VNSTOCK lấy P/E, Market Cap
        try:
            overview = ticker_overview(sym)
            if overview is not None and not overview.empty:
                mcap = round(float(overview['marketcap'].iloc[0]) / 1000, 0) # vnstock trả về tỷ đồng
                pe = round(float(overview['pe'].iloc[0]), 1)
            else:
                mcap, pe = "N/A", "N/A"
        except:
            mcap, pe = "N/A", "N/A"

        data_rows.append([
            sym, exchange, round(close_price, 2), int(avg_vol_20), 
            round(rsi_current, 1), score, trend, mcap, pe, round(gtgd, 1)
        ])
        
        # Nghỉ 0.2s để tránh bị Vnstock/TCBS rate limit
        time.sleep(0.2)
        
    except Exception as e:
        continue

# 5. ĐẨY LÊN SHEET
columns = ['Mã', 'Sàn', 'Đóng cửa (k)', 'KLTB 20N', 'RSI (14)', 'Điểm AI (100)', 'Xu hướng', 'Vốn hóa (tỷ)', 'P/E', 'GTGD (tỷ)']
if data_rows:
    df_result = pd.DataFrame(data_rows, columns=columns).sort_values(by=['Điểm AI (100)', 'GTGD (tỷ)'], ascending=[False, False])
    sheet.clear()
    sheet.update([df_result.columns.values.tolist()] + df_result.values.tolist())
    print(f"THÀNH CÔNG: Đã đẩy {len(data_rows)} mã toàn thị trường lên Sheet!")
else:
    print("CẢNH BÁO: Không tìm thấy dữ liệu!")
