"""SAP 与 Python 之间的数据类型转换工具"""

from datetime import date, datetime, time


def sap_date_to_python(sap_date_str: str | None) -> date | None:
    """将 SAP 日期字符串 (YYYYMMDD) 转换为 Python date 对象"""
    if not sap_date_str or sap_date_str == '00000000':
        return None
    try:
        return date(int(sap_date_str[:4]), int(sap_date_str[4:6]), int(sap_date_str[6:8]))
    except (ValueError, IndexError):
        return None


def python_date_to_sap(d: date | datetime | None) -> str:
    """将 Python date/datetime 转换为 SAP 日期字符串 (YYYYMMDD)"""
    if d is None:
        return '00000000'
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime('%Y%m%d')


def sap_decimal_to_float(value: str | None) -> float | None:
    """将 SAP 的数值字符串转换为 float"""
    if value is None:
        return None
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def sap_to_bool(value: str | None) -> bool:
    """将 SAP 的 X/空 标志转换为 bool"""
    return str(value).strip().upper() == 'X' if value else False


def rows_to_dict_list(rows, columns: list[str]) -> list[dict]:
    """将 SAP RFC 返回的表结构（list of dict）转换为统一的 dict 列表"""
    if not rows:
        return []
    result = []
    for row in rows:
        item = {}
        for col in columns:
            val = row.get(col, None)
            if isinstance(val, str):
                val = val.strip()
            item[col] = val
        result.append(item)
    return result
