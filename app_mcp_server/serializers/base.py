def format_date(dt) -> str:
    """Internal date formatter helper."""
    return dt.strftime("%Y-%m-%d") if dt else "N/A"
