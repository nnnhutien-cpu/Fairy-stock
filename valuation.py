import pandas as pd
from vnstock import ticker_overview

def get_stock_valuation(ticker, ichi_status):
    """
    Hàm cào dữ liệu định giá Cơ bản (P/E, P/B) 
    và kết hợp với Kỹ thuật (Ichimoku) để ra đánh giá.
    """
    try:
        # Cào dữ liệu tài chính của doanh nghiệp
        df = ticker_overview(ticker)
        if not df.empty:
            pe = df['pe'].iloc[0] if 'pe' in df.columns and pd.notna(df['pe'].iloc[0]) else 0.0
            pb = df['pb'].iloc[0] if 'pb' in df.columns and pd.notna(df['pb'].iloc[0]) else 0.0
            pe = round(float(pe), 2)
            pb = round(float(pb), 2)
        else:
            pe, pb = 0.0, 0.0
    except Exception as e:
        pe, pb = 0.0, 0.0

    # THUẬT TOÁN ĐỊNH GIÁ THEO LOGIC CỦA BẠN
    if "Dưới Mây" in str(ichi_status):
        danh_gia = "📉 Định giá Thấp"
    elif "Trên Mây" in str(ichi_status):
        danh_gia = "📈 Định giá Cao"
    else:
        danh_gia = "⚖️ Hợp lý (Trong mây)"

    return {
        "P/E": pe,
        "P/B": pb,
        "Đánh Giá": danh_gia
    }
