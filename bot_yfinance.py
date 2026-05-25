# FORCE UPDATE YFINANCE - VERSION 5.0: ĐA LUỒNG & AI SCORING (0-100)
import os
import json
import requests
import pandas as pd
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)

# ĐIỀN CHÍNH XÁC ID FILE GOOGLE SHEET CỦA BẠN VÀO ĐÂY
sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. HÀM TÍNH TOÁN RSI BẰNG PANDAS (Không cần thư viện ngoài)
def compute_rsi(data, window=14):
    delta = data.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

# 3. LẤY DANH SÁCH MÃ & SÀN TỪ VNDIRECT
print("Đang tải danh sách ~1600 mã chứng khoán từ 3 sàn...")
exchange_map = {}
try:
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock&size=3000"
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json().get('data', [])
    for item in data:
        if len(item['symbol']) == 3:
            sym = item['symbol']
            floor = item.get('floor', 'HOSE').upper()
            exchange_map[sym] = 'HOSE' if floor in ['HSX', 'VNX'] else floor
except Exception:
    print("Dùng danh sách dự phòng...")
    fallback_symbols = ['SSI','VHM','VIC','HPG','VNM','VCB','BID','CTG','TCB','VPB','MBB','STB','ACB','SHB','VIB','HDB','LPB','TPB','MSB','OCB','NVL','PDR','DIG','DXG','VND','VCI','HCM','VIX','SHS','MBS','IDC','PVS','BSR','ACV','VEA','MCH','VGI']
    for s in fallback_symbols: exchange_map[s] = 'HOSE'

symbols = list(exchange_map.keys())

# --- DANH SÁCH VIP (Được ưu tiên qua màng lọc) ---
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 4. HÀM XỬ LÝ TỪNG MÃ CHỨNG KHOÁN (Dành cho Đa luồng)
def process_ticker(sym):
    try:
        exchange = exchange_map.get(sym, 'HOSE')
        # Tự động nắn đuôi mã cho chuẩn Yahoo Finance
        y_sym = f"{sym}.HN" if exchange == 'HNX' else f"{sym}.VN"
        ticker = yf.Ticker(y_sym)
        df = ticker.history(period="3mo") # Lấy 3 tháng để tính RSI cho chuẩn
        
        # Nếu UPCoM tìm .VN không ra, tự lật sang .HN
        if df.empty and exchange == 'UPCOM':
            ticker = yf.Ticker(f"{sym}.HN")
            df = ticker.history(period="3mo")

        if df.empty or len(df) < 30: 
            return None

        # Tính RSI trước khi cắt 20 ngày
        df['RSI'] = compute_rsi(df['Close'], 14)
        
        # Cắt lấy 20 ngày gần nhất
        df = df.tail(20)
        close_price = float(df['Close'].iloc[-1])
        close_kvnd = close_price / 1000
        avg_vol_20 = float(df['Volume'].mean())
        last_vol = float(df['Volume'].iloc[-1])
        gtgd = (close_price * avg_vol_20) / 1000000000
        rsi_current = float(df['RSI'].iloc[-1])
        
        # BỘ LỌC THANH KHOẢN > 20 TỶ (Ngoại trừ VIP)
        if gtgd <= 20 and sym not in vip_symbols:
            return None

        ma20 = float(df['Close'].mean())
        
        # --- HỆ THỐNG CHẤM ĐIỂM AI (0-100) ---
        score = 0
        # 1. Điểm Xu hướng (Trend - 40đ)
        if close_price > ma20 * 1.02: score += 40
        elif close_price > ma20: score += 25
        else: score += 10
        
        # 2. Điểm Động lượng (RSI - 30đ)
        if 50 <= rsi_current <= 65: score += 30 # Vùng tăng trưởng đẹp
        elif 65 < rsi_current <= 75: score += 20 # Sắp quá mua
        elif 40 <= rsi_current < 50: score += 15 # Tích lũy
        else: score += 5 # Quá bán hoặc Quá mua rủi ro cao

        # 3. Điểm Dòng tiền (Volume - 30đ)
        if last_vol > avg_vol_20 * 1.5: score += 30 # Dòng tiền đột biến
        elif last_vol > avg_vol_20 * 1.1: score += 20
        else: score += 10

        # Phân loại Xu hướng dựa trên điểm số
        if score >= 75: trend = "TÍCH CỰC"
        elif score >= 50: trend = "TRUNG TÍNH"
        else: trend = "TIÊU CỰC"

        # Lấy thông tin cơ bản
        try:
            info = ticker.info
            mcap = round(info.get('marketCap', 0) / 1000000000, 0) if info.get('marketCap') else "N/A"
            pe = round(info.get('trailingPE', 0), 1) if info.get('trailingPE') else "N/A"
        except:
            mcap, pe = "N/A", "N/A"

        return [sym, exchange, round(close_kvnd, 2), int(avg_vol_20), round(rsi_current, 1), score, trend, mcap, pe, round(gtgd, 1)]
    except Exception:
        return None

# 5. ÉP CHẠY ĐA LUỒNG (ĐẨY TỐC ĐỘ GẤP 10 LẦN)
data_rows = []
print(f"Bắt đầu quét {len(symbols)} mã bằng chế độ Đa luồng (Multithreading)...")

# Dùng 15 luồng công nhân cùng lúc thay vì chạy từng mã
with ThreadPoolExecutor(max_workers=15) as executor:
    futures = {executor.submit(process_ticker, sym): sym for sym in symbols}
    for future in as_completed(futures):
        result = future.result()
        if result:
            data_rows.append(result)

# 6. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã', 'Sàn', 'Đóng cửa (k)', 'KLTB 20N', 'RSI (14)', 'Điểm AI (100)', 'Xu hướng', 'Vốn hóa (tỷ)', 'P/E', 'GTGD (tỷ)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['Điểm AI (100)', 'GTGD (tỷ)'], ascending=[False, False])
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"THÀNH CÔNG: Đã đẩy {len(data_rows)} mã lên Sheet chỉ trong chớp mắt!")
else:
    print("CẢNH BÁO: Không có dữ liệu!")
