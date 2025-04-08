import datetime as dt
import pandas as pd

def format_timestamp(timestamp):
    """
    Format a timestamp for display
    
    Args:
        timestamp: Timestamp to format
        
    Returns:
        Formatted timestamp string
    """
    if pd.isna(timestamp):
        return "N/A"
        
    if isinstance(timestamp, str):
        try:
            timestamp = pd.to_datetime(timestamp)
        except:
            return "Invalid date"
    
    try:
        return timestamp.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return "Invalid date"

def calculate_check_duration_minutes(start_time, end_time):
    """
    Calculate duration of a check in minutes
    
    Args:
        start_time: Start timestamp
        end_time: End timestamp
        
    Returns:
        Duration in minutes
    """
    if not start_time or not end_time:
        return 0
        
    if isinstance(start_time, str):
        start_time = pd.to_datetime(start_time)
    
    if isinstance(end_time, str):
        end_time = pd.to_datetime(end_time)
    
    try:
        duration = (end_time - start_time).total_seconds() / 60
        return round(duration, 1)
    except:
        return 0

def get_time_bounds(period):
    """
    Get time bounds for a specified time period
    
    Args:
        period: String specifying period ('today', 'week', 'month', 'year')
        
    Returns:
        Tuple of (start_date, end_date)
    """
    end_date = dt.datetime.now()
    
    if period == 'today':
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = end_date - dt.timedelta(days=7)
    elif period == 'month':
        start_date = end_date - dt.timedelta(days=30)
    elif period == 'year':
        start_date = end_date - dt.timedelta(days=365)
    else:  # Default to week
        start_date = end_date - dt.timedelta(days=7)
    
    return start_date, end_date
