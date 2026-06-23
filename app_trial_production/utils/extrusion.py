from django.utils import timezone


def is_all_day_event(start_dt, end_dt):
    """约定：开始和结束时间均为本地 0 时 → 全天事件

    用于 FullCalendar 事件渲染判断，将 UTC 时间转为本地时区后检查。
    """
    if end_dt is None:
        return False
    if start_dt.tzinfo is not None:
        local_tz = timezone.get_current_timezone()
        start_dt = start_dt.astimezone(local_tz)
        end_dt = end_dt.astimezone(local_tz)
    return (
        start_dt.hour == 0 and start_dt.minute == 0 and start_dt.second == 0 and
        end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0
    )
