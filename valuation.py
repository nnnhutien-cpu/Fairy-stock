import pandas as pd

def get_stock_valuation(ticker, ichi_status, price_val):
    """
    Hàm cào dữ liệu định giá Cơ bản (P/E, P/B, Vốn hóa) 
    và kết hợp với Kỹ thuật (Ichimoku) để ra đánh giá.
    """
    pe, pb, von_hoa = 0.0, 0.0, 0.0
    
    # 1. Cào Overview để lấy Khối lượng lưu hành (Tính Vốn hóa)
    try:
        try:
            from vnstock.stock import ticker_overview
        except ImportError:
            from vnstock import ticker_overview
            
        df_overview = ticker_overview(ticker)
        if df_overview is not None and not df_overview.empty:
            df_overview.columns = [str(c).lower().strip() for c in df_overview.columns]
            
            # Tính Vốn hóa (Market Cap)
            if 'outstandingshare' in df_overview.columns:
                # Giá vnstock đôi khi trả về 22.5 (Ngàn VNĐ) hoặc 22500 (VNĐ), ta chuẩn hóa về VNĐ
                p_vnd = price_val * 1000 if price_val < 500 else price_val
                out_share = float(df_overview['outstandingshare'].iloc[0]) # Đơn vị: Triệu CP
                von_hoa = (out_share * p_vnd) / 1000 # Ra đơn vị Tỷ VNĐ
            
            # Nếu trong overview có sẵn pe, pb thì lấy luôn
            if 'pe' in df_overview.columns: pe = df_overview['pe'].iloc[0]
            if 'pb' in df_overview.columns: pb = df_overview['pb'].iloc[0]
    except Exception as e:
        pass

    # 2. Nếu P/E và P/B vẫn bằng 0, ta gọi "đệ tử" Financial Ratio ra để đào dữ liệu
    if pe == 0.0 and pb == 0.0:
        try:
            try:
                from vnstock.stock import financial_ratio
            except ImportError:
                from vnstock import financial_ratio
                
            df_ratio = financial_ratio(ticker, 'quarterly', True)
            if df_ratio is not None and not df_ratio.empty:
                df_ratio.columns = [str(c).lower().strip() for c in df_ratio.columns]
                
                if 'pe' in df_ratio.columns: pe = df_ratio['pe'].iloc[0]
                elif 'pricetoearning' in df_ratio.columns: pe = df_ratio['pricetoearning'].iloc[0]
                    
                if 'pb' in df_ratio.columns: pb = df_ratio['pb'].iloc[0]
                elif 'pricetobook' in df_ratio.columns: pb = df_ratio['pricetobook'].iloc[0]
        except Exception as e:
            pass

    # Làm sạch số liệu (Xóa bỏ các số lỗi)
    pe = round(float(pe), 2) if pd.notna(pe) else 0.0
    pb = round(float(pb), 2) if pd.notna(pb) else 0.0
    von_hoa = round(float(von_hoa), 2) if pd.notna(von_hoa) else 0.0

    # THUẬT TOÁN ĐỊNH GIÁ KẾT HỢP ICHIMOKU
    if pe == 0.0 and pb == 0.0:
        danh_gia = "⚠️ Đang tính toán"
    elif "Dưới Mây" in str(ichi_status):
        danh_gia = "📉 Định giá Thấp (Rẻ)"
    elif "Trên Mây" in str(ichi_status):
        danh_gia = "📈 Định giá Cao (Đắt)"
    else:
        danh_gia = "⚖️ Hợp lý (Trong mây)"

    return {
        "P/E": pe,
        "P/B": pb,
        "Vốn Hóa (Tỷ)": von_hoa,
        "Đánh Giá": danh_gia
    }
