import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from datetime import datetime, timedelta, timezone
import time
import sys

# ==========================================
# 0. CẤU HÌNH NGUỒN GIÁ TCBS
# ==========================================
ICT = timezone(timedelta(hours=7))  # GitHub Actions chạy giờ UTC -> luôn quy đổi về giờ VN
TCBS_URL = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
CLOSE_HOUR = 15          # sau 15:00 ICT nến ngày mới coi là đã chốt
PRICE_DIVISOR = 1        # đổi thành 1000 nếu sheet cũ lưu giá theo nghìn đồng (VD 60.5 thay vì 60500)
MIN_OK_RATIO = 0.8       # tối thiểu 80% số mã phải cào được, nếu không báo lỗi đỏ

# ==========================================
# 1. CẤU HÌNH KẾT NỐI BẰNG ID (CHỐNG LỖI 100%)
# ==========================================
SHEET_ID = "1r0cokW2bV7L-x8i1HWS0Cg3nOVak8VYN0vkzR5FgzNI"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Đảm bảo file credentials.json nằm cùng thư mục
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
client = gspread.authorize(CREDS)

try:
    # DÙNG ID THAY VÌ TÊN ĐỂ KHÔNG BAO GIỜ SỢ ĐỔI TÊN BỊ LỖI
    worksheet = client.open_by_key(SHEET_ID).worksheet("data")
    print("✅ Đã kết nối thành công tới Sheet 'data'!")
except Exception as e:
    print(f"❌ Lỗi kết nối Google Sheets: {e}")
    sys.exit(1)  # Báo lỗi đỏ cho GitHub biết để dừng lại

# ==========================================
# 2. DANH SÁCH MÃ CẦN CÀO & PHIÊN KỲ VỌNG
# ==========================================
tickers = ['PLX', 'VNM', 'FPT', 'SSI', 'HPG', 'MWG', 'TCB', 'VPB', 'VCB']
print(f"⏳ Đang tiến hành cào {len(tickers)} mã cổ phiếu từ TCBS...")


def expected_session(now):
    """Phiên kỳ vọng: hôm nay nếu đã qua 15:00 ICT, ngược lại là phiên trước; bỏ T7/CN.
    (Chưa xử lý ngày lễ.)"""
    d = now.date() if now.hour >= CLOSE_HOUR else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def fetch_tcbs_latest(ticker, http, now, retries=3):
    """Lấy nến ngày mới nhất đã chốt của 1 mã từ TCBS. Trả về dict hoặc None."""
    to_ts = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    params = {"ticker": ticker, "type": "stock", "resolution": "D",
              "to": to_ts, "countBack": 5}  # 5 nến lùi lại -> luôn trúng phiên gần nhất
    for attempt in range(retries):
        try:
            r = http.get(TCBS_URL, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            bars = r.json().get("data") or []
            if not bars:
                return None
            # Trước giờ đóng cửa, nến của hôm nay là nến đang chạy dở -> bỏ
            if now.hour < CLOSE_HOUR and bars[-1]["tradingDate"][:10] == now.date().isoformat():
                bars = bars[:-1]
                if not bars:
                    return None
            b = bars[-1]
            return {
                'symbol': ticker,
                'date': b["tradingDate"][:10],  # YYYY-MM-DD
                'high': b["high"] / PRICE_DIVISOR,
                'low': b["low"] / PRICE_DIVISOR,
                'open': b["open"] / PRICE_DIVISOR,
                'close': b["close"] / PRICE_DIVISOR,
                'volume': b["volume"],
            }
        except Exception as e:
            if attempt == retries - 1:
                print(f"⚠️ Lỗi khi cào mã {ticker}: {e}")
            else:
                time.sleep(1.5 * (attempt + 1))
    return None


# ==========================================
# 3. TIẾN HÀNH CÀO VÀ LỌC DỮ LIỆU
# ==========================================
now = datetime.now(ICT)
exp = expected_session(now)
print(f"🕒 Bây giờ: {now:%Y-%m-%d %H:%M} ICT · Phiên kỳ vọng: {exp}")

all_data = []
http = requests.Session()
for ticker in tickers:
    row = fetch_tcbs_latest(ticker, http, now)
    if row:
        all_data.append(row)
        print(f"   + Cào thành công: {ticker} ({row['date']})")
    time.sleep(0.3)  # Nghỉ chống block IP

# Kiểm tra độ đầy đủ và độ mới của dữ liệu
if len(all_data) < MIN_OK_RATIO * len(tickers):
    print(f"❌ Chỉ cào được {len(all_data)}/{len(tickers)} mã, dưới ngưỡng {MIN_OK_RATIO:.0%}. Không ghi đè sheet.")
    sys.exit(1)

stale = [r['symbol'] for r in all_data if r['date'] < exp.isoformat()]
if stale:
    print(f"⚠️ {len(stale)} mã chưa có phiên {exp}: {', '.join(stale)}")
else:
    print(f"✅ Toàn bộ {len(all_data)} mã đã có phiên {exp}")

# ==========================================
# 4. ĐẨY LÊN GOOGLE SHEETS
# ==========================================
if all_data:
    df_final = pd.DataFrame(all_data)
    worksheet.clear()

    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()

    # Đẩy lên Google Sheet chuẩn phiên bản mới
    worksheet.update(values=data_to_upload, range_name='A1')

    print(f"🎉 HOÀN TẤT! Đã đẩy {len(df_final)} hàng dữ liệu lên Google Sheets.")
else:
    print("❌ Không có dữ liệu nào được cào về.")
    sys.exit(1)
