import streamlit as st
import pandas as pd
import time
import threading
from datetime import datetime, timedelta
from vnstock.api.quote import Quote
from vnstock.api.listing import Listing

# ==========================================================
# CACHE DÀI HẠN TỪ SUPABASE (DO BOT NỀN BƠM SẴN 1 LẦN/NGÀY)
# ==========================================================
# Đây là chìa khoá để quét NHANH thật sự (vài giây cho hàng trăm mã):
# thay vì gọi API sống cho từng mã lúc người dùng bấm "Quét" (luôn bị giới hạn
# 20-60 request/phút của vnstock), 1 bot chạy nền (GitHub Actions, xem
# bulk_fetch_prices.py) lấy sẵn dữ liệu 1 lần/ngày sau giờ đóng cửa và lưu vào
# bảng `stock_prices` trên Supabase. Khi quét, app chỉ ĐỌC DB (không gọi API)
# -> không còn bị giới hạn tốc độ, 500 mã đọc từ DB chỉ mất vài giây.
# Nếu chưa chạy bot nền / mã không có trong cache -> tự động rơi về gọi API sống
# như bình thường (chậm hơn nhưng luôn ra kết quả đúng).
_supabase_client = None
_supabase_tried = False

def _get_supabase():
    global _supabase_client, _supabase_tried
    if _supabase_tried:
        return _supabase_client
    _supabase_tried = True
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        _supabase_client = create_client(url, key)
    except Exception:
        _supabase_client = None
    return _supabase_client

def _read_from_cache(ticker, days_back, max_staleness_days=4):
    """Đọc lịch sử giá từ Supabase nếu có và đủ mới. Trả về None nếu không có/quá cũ -> gọi API sống."""
    sb = _get_supabase()
    if sb is None:
        return None
    try:
        resp = (
            sb.table("stock_prices")
            .select("date,open,high,low,close,volume")
            .eq("ticker", ticker)
            .order("date", desc=True)
            .limit(int(days_back * 1.6) + 10)  # dư ra để bù ngày nghỉ/lễ
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None

        newest_date = pd.to_datetime(rows[0]["date"])
        if (datetime.now() - newest_date).days > max_staleness_days:
            return None  # cache quá cũ (bot nền có thể đã ngừng chạy) -> gọi API sống cho chắc

        df = pd.DataFrame(rows)
        df = df.rename(columns={"date": "time"})
        return _normalize(df)
    except Exception:
        return None  # bảng chưa tồn tại / lỗi kết nối -> im lặng rơi về API sống, không làm sập app

# ==========================================================
# TỰ GIỚI HẠN TỐC ĐỘ GỌI API (CHỦ ĐỘNG) THAY VÌ ĐỂ VNSTOCK TỰ CHẶN RỒI RETRY
# ==========================================================
# vnstock (bản >=4) có cơ chế rate-limit NGẦM: khách chưa đăng ký API key chỉ được
# 20 request/phút. Khi vượt hạn mức, thư viện không báo lỗi ngay mà tự "sleep" rồi
# retry nhiều lần bên trong -> khiến app trông như bị "treo" dù vẫn đang chạy.
# Giải pháp: chủ động rải đều request theo đúng nhịp cho phép, KHÔNG bao giờ để
# thư viện phải tự chặn -> tốc độ ổn định, có thể ước tính chính xác, không bị "kẹt".
_rate_lock = threading.Lock()
from collections import deque
_call_timestamps = deque()   # deque: popleft() O(1) thay vì list.pop(0) O(n)
_rate_limit_per_min = 18

def set_rate_limit(requests_per_minute: int):
    """Gọi từ main.py khi có API key để tăng tốc (vd: 55/phút)."""
    global _rate_limit_per_min
    _rate_limit_per_min = max(1, int(requests_per_minute))

def _throttle():
    with _rate_lock:
        now = time.time()
        cutoff = now - 60
        while _call_timestamps and _call_timestamps[0] < cutoff:
            _call_timestamps.popleft()
        if len(_call_timestamps) >= _rate_limit_per_min:
            wait = 60 - (now - _call_timestamps[0]) + 0.05  # 50ms padding, bớt 50ms so với trước
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            cutoff = now - 60
            while _call_timestamps and _call_timestamps[0] < cutoff:
                _call_timestamps.popleft()
        _call_timestamps.append(now)

# Danh sách dự phòng nếu xui xẻo cả 3 CTCK cùng sập API
FALLBACK_TICKERS = ["HPG", "SSI", "VND", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]

def _normalize(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    if 'date' in df.columns and 'time' not in df.columns:
        df.rename(columns={'date': 'time'}, inplace=True)
        
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
        # LỌC MÚI GIỜ (TZ-NAIVE): Xóa timezone để không bị lỗi crash khi trừ ngày tháng ở main.py
        if getattr(df['time'].dt, 'tz', None) is not None:
            df['time'] = df['time'].dt.tz_localize(None)
            
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    if 'time' in df.columns:
        df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
        
    return df

def _fetch_yahoo(symbol, start, end):
    try:
        import yfinance as yf
        # FIX LỖI: VNINDEX trên Yahoo tên là ^VNINDEX, không phải VNINDEX.VN
        yf_symbol = "^VNINDEX" if symbol == "VNINDEX" else f"{symbol}.VN"
        
        df = yf.download(yf_symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
            
        df = df.reset_index()
        # Xử lý Multi-Index cột của bản yfinance mới nhất
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.columns = [str(c).lower().strip() for c in df.columns]
        
        if 'date' in df.columns:
            df.rename(columns={'date': 'time'}, inplace=True)
            
        return _normalize(df)
    except Exception:
        return pd.DataFrame()

def _fetch_one(symbol, start, end, interval, src, timeout=12):
    """Gọi 1 nguồn với timeout cứng — tránh bị treo vô hạn khi API chậm."""
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(
            lambda: Quote(symbol=symbol, source=src).history(
                start=start, end=end, interval=interval
            )
        )
        try:
            df = fut.result(timeout=timeout)
            if df is not None and not df.empty:
                return _normalize(df)
        except Exception:
            pass
    return None

def _fetch(symbol, start, end, interval):
    """Fallback chain: VCI → MSN → Yahoo (chỉ 1D). Mỗi nguồn có timeout 12s."""
    sources = ['VCI', 'MSN']
    for src in sources:
        _throttle()
        result = _fetch_one(symbol, start, end, interval, src, timeout=12)
        if result is not None:
            return result

    # Nếu cả nội địa đều sập, cầu cứu Yahoo Finance
    if interval == '1D':
        return _fetch_yahoo(symbol, start, end)

    return pd.DataFrame()

@st.cache_data(ttl=86400) # Lưu cache danh sách mã trong 24h
def get_all_tickers(exchange='all'):
    # LƯU Ý: all_symbols() ở vnstock>=4.x chỉ trả về 2 cột (symbol, organ_name),
    # KHÔNG còn cột 'exchange'/'type' -> lọc theo sàn sẽ không có tác dụng.
    # Dùng thẳng symbols_by_exchange() vì hàm này mới thực sự có đủ cột exchange/type.
    for src in ['vci', 'kbs']:
        try:
            _throttle()
            df = Listing(source=src).symbols_by_exchange()
            df.columns = [str(c).lower().strip() for c in df.columns]

            # Tìm cột phân loại (Stock, Bond, CW...) để chỉ lấy cổ phiếu
            type_col = next((c for c in df.columns if 'type' in c), None)
            if type_col:
                df = df[df[type_col].astype(str).str.upper().isin(['STOCK', 'CP', 'CỔ PHIẾU'])]

            if 'exchange' in df.columns:
                df = df[df['exchange'].astype(str).str.upper().isin(['HOSE', 'HSX', 'HNX', 'UPCOM'])]
                if exchange != 'all':
                    tgt = ['HOSE', 'HSX'] if str(exchange).upper() in ('HOSE', 'HSX') else [str(exchange).upper()]
                    df = df[df['exchange'].astype(str).str.upper().isin(tgt)]

            col = 'symbol' if 'symbol' in df.columns else ('ticker' if 'ticker' in df.columns else None)

            if col:
                lst = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
                if lst:
                    return lst
        except Exception:
            continue

    # Chỉ khi mạng rớt sạch thì mới phải dùng 10 mã dự bị
    return FALLBACK_TICKERS

def _ttl_until_next_open():
    """
    Trả về số giây còn lại đến 9:00 sáng ngày giao dịch tiếp theo.
    Dữ liệu kết phiên (1D) không thay đổi cho đến khi phiên mới mở —
    cache đến lúc đó giúp tránh hoàn toàn việc refetch thừa trong phiên.
    """
    now = datetime.now()
    # Nếu trước 9:00 sáng hôm nay -> cache đến 9:00 hôm nay
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        # Sau 9:00 -> cache đến 9:00 ngày mai (bỏ qua cuối tuần không cần thiết)
        target += timedelta(days=1)
    return max(int((target - now).total_seconds()), 300)  # tối thiểu 5 phút

@st.cache_data(ttl=_ttl_until_next_open(), show_spinner=False)
def get_stock_data(ticker, days_back=200):
    """Dữ liệu lịch sử 1D — cache đến đầu phiên kế tiếp, không refetch trong phiên."""
    cached = _read_from_cache(ticker, days_back)
    if cached is not None and len(cached) >= min(60, days_back // 2):
        return cached
    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch(ticker, start_date, end_date, '1D')

@st.cache_data(ttl=_ttl_until_next_open(), show_spinner=False)
def get_vnindex_data(ticker="VNINDEX", days_back=365):
    """Dữ liệu lịch sử VNINDEX 1D — cache đến đầu phiên kế tiếp."""
    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    return _fetch('VNINDEX', start_date, end_date, '1D')

@st.cache_data(ttl=30, show_spinner=False)
def get_intraday_vnindex():
    """Dữ liệu tick 1m — cache 30s, dùng riêng cho Tab 1 (real-time chart)."""
    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    df = _fetch('VNINDEX', start_date, end_date, '1m')
    return df if not df.empty else pd.DataFrame()
