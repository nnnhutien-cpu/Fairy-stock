# bot_ichimoku_alert.py
# Chạy bởi daily_update.yml — không tạo workflow mới
# Dùng lại data_loader + indicators đã có sẵn

import sys
sys.path.insert(0, ".")

from data_loader import get_stock_data
from indicators  import calculate_technical_signals
# từ bot_reports import send_telegram (nếu có)

WATCHLIST = ["HPG", "VIC", "FPT", "TCB", "MBB"]

def run():
    buy_list, sell_list = [], []
    for sym in WATCHLIST:
        df = get_stock_data(sym, days_back=350)
        if df is None or len(df) < 150:
            continue
        result = calculate_technical_signals(df, sym)
        if result is None:
            continue
        xu_huong = result.get("Xu Hướng", "")
        if "Tăng" in xu_huong:
            buy_list.append(f"{sym} ({result['Cách Knife129 (%)']:+.1f}%)")
        elif "Giảm" in xu_huong:
            sell_list.append(sym)
    
    # Build Telegram message
    msg = "📊 <b>Cô Tiên Bot — Báo Cáo Xu Hướng</b>\n"
    if buy_list:
        msg += f"🟢 Tăng: {', '.join(buy_list)}\n"
    if sell_list:
        msg += f"🔴 Giảm: {', '.join(sell_list)}\n"
    if not buy_list and not sell_list:
        msg += "⚪ Không có tín hiệu mới\n"
    
    print(msg)
    # send_telegram(msg)  ← bỏ comment khi có bot_reports

if __name__ == "__main__":
    run()
