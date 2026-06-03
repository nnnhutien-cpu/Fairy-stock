from vnstock import stock_historical_data
from datetime import datetime, timedelta

def get_stock_data(symbol, days_back=365):
    """Cào dữ liệu cổ phiếu (Lấy lùi lại 1 năm để đủ tính MA200)"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=symbol, 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="1D", type="stock")
        return df
    except Exception as e:
        return None

def get_vnindex_data():
    """Cào dữ liệu chỉ số VN-INDEX 7 ngày gần nhất"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol='VNINDEX', 
                                   start_date=start_date, 
                                   end_date=end_date, 
                                   resolution="1D", type="index")
        return df
    except Exception as e:
        return None
