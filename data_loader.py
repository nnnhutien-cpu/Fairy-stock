from vnstock import stock_historical_data

def get_stock_data(symbol, start_date, end_date):
    """Hàm này chuyên đi cào dữ liệu từ vnstock"""
    try:
        df = stock_historical_data(symbol=symbol, 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="1D", type="stock")
        return df
    except Exception as e:
        return None
