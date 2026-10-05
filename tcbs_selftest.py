"""
Chạy: python tcbs_selftest.py
Kiểm tra từng endpoint TCBS từ máy/CI của bạn và in kết quả PASS/FAIL.
"""
from datetime import datetime, timedelta

import tcbs_client as t

end = datetime.now().strftime("%Y-%m-%d")
start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


df = t.history("HPG", start, end, "1D")
check("Giá cổ phiếu HPG (1D)", not df.empty,
      f"-> {len(df)} nến, close cuối = {df['close'].iloc[-1] if not df.empty else None}")

df = t.history("VNINDEX", start, end, "1D")
check("Chỉ số VNINDEX (1D)", not df.empty,
      f"-> {len(df)} nến, close cuối = {df['close'].iloc[-1] if not df.empty else None}")

df = t.history("VNINDEX", (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"), end, "1m")
check("VNINDEX 1 phút (intraday)", not df.empty, f"-> {len(df)} nến")

df = t.history("HPG", (datetime.now() - timedelta(days=500)).strftime("%Y-%m-%d"), end, "1D")
check("HPG 500 ngày (test chia đoạn)", len(df) > 250, f"-> {len(df)} nến")

ov = t.overview("HPG")
check("Overview HPG", bool(ov), f"-> exchange={ov.get('exchange')}, outstandingShare={ov.get('outstandingShare')}")

rt = t.financial_ratio("HPG")
check("Financial ratio HPG", not rt.empty,
      f"-> P/E={rt['priceToEarning'].iloc[0] if not rt.empty and 'priceToEarning' in rt else None}")

snap = t.valuation_snapshot("HPG", price_vnd=20000)
check("Valuation snapshot", snap["pe"] > 0 or snap["pb"] > 0, f"-> {snap}")

syms = t.list_symbols("all")
check("tickers.json", len(syms) > 100, f"-> {len(syms)} mã")

print("\nLỗi gần nhất:", t.get_last_error())
