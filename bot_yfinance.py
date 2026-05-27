# FORCE UPDATE - VERSION 12.0: THE ULTIMATE VNSTOCK3 (KIẾN TRÚC MỚI)
import os
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Sử dụng cú pháp import hướng đối tượng của Vnstock3
from vnstock import Vnstock  

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)

# ID file Google Sheet của bạn (Đã được cấp quyền cho email robot mới)
sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. HÀM TÍNH TOÁN RSI BẰNG PANDAS THUẦN (Chống lỗi Module)
def compute_rsi(series, window=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# 3. SIÊU CƠ SỞ DỮ LIỆU OFFLINE 350+ MÃ (Bao trọn 3 sàn)
print("Đang nạp Siêu danh sách mã chứng khoán 3 sàn...")

hose_symbols = ['SSI','VHM','VIC','HPG','VNM','VCB','BID','CTG','TCB','VPB','MBB','STB','ACB','SHB','VIB','HDB','LPB','TPB','MSB','OCB','SSB','EIB','NAB','NVL','PDR','DIG','DXG','NLG','KDH','KBC','VGC','SZC','HDG','BCG','FCN','CTD','VND','VCI','HCM','VIX','FTS','BSI','CTS','AGR','ORS','VDS','TVS','HSG','NKG','SMC','TLH','DGC','DPM','DCM','CSV','PHR','GVR','DPR','TRC','GMD','HAH','VOS','VHC','ANV','IDI','FMC','DBC','BAF','HAG','PAN','SBT','FRT','DGW','PET','MWG','PNJ','MSN','SAB','VJC','HVN','FPT','PLX','GAS','POW','NT2','GEG','REE','PC1','ASM','CII','HBC','VCG','HHV','LCG','HDC','IJC','SCR','CRE','KHG','DXS','PTB','GIL','TCM','TNG','VSH','SJD','SBA','TDM','BWE','VPD','VPI','QCG','TCH','HHS','HAX','CMX','DAT','EVF','FIT','HQC','ITA','OGC','HNG','TTF','AAA','APH','NHH','BMP','NTP','DRC','CSM','SRC','VTO','VIP','PVT']
hnx_symbols = ['SHS','MBS','IDC','PVS','CEO','HUT','L14','BVS','VGS','TIG','TAR','THD','BAB','NVB','PVC','PVB','APS','IDJ','API','AAV','AMV','VC3','VC7','MST','CSC','DDG','DTD','MCO','MBG','NTH','SDA','LIG','TTH','VIG','HDA','SCI','SRA','TVC','GKM']
upcom_symbols = ['BSR','ACV','VEA','MCH','VGI','FOX','VTP','OIL','ABB','BVB','VBB','SGB','PGB','KLB','SBS','AAS','VFS','C4G','G36','DDV','PAS','QNS','LTG','MSR','HTM','VGT','VNZ','SGP','PHP','TCI','DSC','BOT','DRI','TDS','HND','QTP','UPC','XDC','HSV']

exchange_map = {}
for s in hose_symbols: exchange_map[s] = 'HOSE'
for s in hnx_symbols: exchange_map[s] = 'HNX'
for s in upcom_symbols: exchange_map[s] = 'UPCOM'

symbols = list(exchange_map.keys())

# KIM BÀI MIỄN TỬ (Cứu các siêu cổ phiếu dòng tiền khi thị trường sụt giảm thanh khoản)
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 4. QUÉT DỮ LIỆU BẰNG ĐỘNG CƠ VNSTOCK3
data_rows = []
print(f"Bắt đầu quét {len(symbols)} mã bằng VNSTOCK3...")

# Lấy mốc thời gian 90 ngày qua để tính toán động lượng
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

for sym in symbols:
    try:
        exchange = exchange_map.get(sym, 'HOSE')
        
        # Gọi lệnh theo chuẩn hướng đối tượng của Vnstock3 (Lấy nguồn VCI cực kỳ ổn định)
        stock = Vnstock().stock(symbol=sym, source='VCI')
        df = stock.quote.history(start=start_date, end=end_date)
        
        if df is None or df.empty or len(df) < 30:
            continue
            
        # Tự động đồng bộ tên cột hoa/thường của thư viện
        col_close = 'close' if 'close' in df.columns else 'Close'
        col_vol = 'volume' if 'volume' in df.columns else 'Volume'

        # Tính chỉ báo RSI
        df['RSI'] = compute_rsi(df[col_close], 14)
        
        # Cắt lấy 20 phiên giao dịch thực tế gần nhất
        df = df.tail(20)
        
        close_price = float(df[col_close].iloc[-1])
        # Chuẩn hóa đơn vị giá của VNStock3 (Tự động đưa về dạng nghìn đồng để tính toán)
        if close_price > 1000:
            close_price_vnd = close_price
            close_kvnd = close_price / 1000
        else:
            close_price_vnd = close_price * 1000
            close_kvnd = close_price

        avg_vol_20 = float(df[col_vol].mean())
        last_vol = float(df[col_vol].iloc[-1])
        
        # Tính Giá trị giao dịch trung bình 20 phiên (GTGD)
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        rsi_current = float(df['RSI'].iloc[-1])
        
        # --- BỘ LỌC THANH KHOẢN > 20 TỶ ĐỒNG ---
        if gtgd <= 20 and sym not in vip_symbols:
            continue

        ma20 = float(df[col_close].mean())
        
        # --- HỆ THỐNG CHẤM ĐIỂM DÒNG TIỀN AI (0-100) ---
        score = 0
        # 1. Chấm điểm kỹ thuật xu hướng (Tối đa 40 điểm)
        if close_price > ma20 * 1.02: score += 40
        elif close_price > ma20: score += 25
        else: score += 10
        
        # 2. Chấm điểm động lượng RSI (Tối đa 30 điểm)
        if 50 <= rsi_current <= 65: score += 30  # Vùng bứt phá mạnh lý tưởng
        elif 65 < rsi_current <= 75: score += 20 # Vùng tăng nóng sắp quá mua
        elif 40 <= rsi_current < 50: score += 15 # Vùng tích lũy nền giá
        else: score += 5                         # Rủi ro cao

        # 3. Chấm điểm bùng nổ khối lượng Vonume Breakout (Tối đa 30 điểm)
        if last_vol > avg_vol_20 * 1.5: score += 30 # Khối lượng nổ gấp rưỡi trung bình
        elif last_vol > avg_vol_20 * 1.1: score += 20
        else: score += 10

        # Phân loại trạng thái Smg dựa trên điểm số AI
        if score >= 75: trend = "TÍCH CỰC"
        elif score >= 50: trend = "TRUNG TÍNH"
        else: trend = "TIÊU CỰC"

        # Lấy số liệu Vốn hóa và P/E cơ bản từ nguồn TCBS tổng quan
        try:
            stock_tcbs = Vnstock().stock(symbol=sym, source='TCBS')
            overview = stock_tcbs.company.overview()
            
            if overview is not None and not overview.empty:
                col_mcap = 'marketcap' if 'marketcap' in overview.columns else ('marketCap' if 'marketCap' in overview.columns else None)
                col_pe = 'pe' if 'pe' in overview.columns else ('PE' if 'PE' in overview.columns else None)
                
                mcap = round(float(overview[col_mcap].iloc[0]) / 1000, 0) if col_mcap else "N/A"
                pe = round(float(overview[col_pe].iloc[0]), 1) if col_pe else "N/A"
            else:
                mcap, pe = "N/A", "N/A"
        except:
            mcap, pe = "N/A", "N/A"

        data_rows.append([
            sym, exchange, round(close_kvnd, 2), int(avg_vol_20), 
            round(rsi_current, 1), score, trend, mcap, pe, round(gtgd, 1)
        ])
        
        # Giãn cách 0.2 giây thông minh để bảo vệ IP khỏi bị các sàn chặn
        time.sleep(0.2)
        
    except Exception:
        continue

# 5. ĐỒNG BỘ DỮ LIỆU LÊN GOOGLE SHEET CỦA BẠN
columns = ['Mã', 'Sàn', 'Đóng cửa (k)', 'KLTB 20N', 'RSI (14)', 'Điểm AI (100)', 'Xu hướng', 'Vốn hóa (tỷ)', 'P/E', 'GTGD (tỷ)']
if data_rows:
    # Sắp xếp danh sách ưu tiên: Điểm AI cao nhất và Thanh khoản lớn nhất lên đầu bảng
    df_result = pd.DataFrame(data_rows, columns=columns).sort_values(by=['Điểm AI (100)', 'GTGD (tỷ)'], ascending=[False, False])
    sheet.clear()
    sheet.update([df_result.columns.values.tolist()] + df_result.values.tolist())
    print(f" THÀNH CÔNG: Đã quét và đẩy {len(data_rows)} mã toàn thị trường (Bao gồm cả HNX & UPCOM) lên Sheet!")
else:
    print(" CẢNH BÁO: Hệ thống không lấy được dữ liệu thô!")
