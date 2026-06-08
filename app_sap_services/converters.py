"""
SAP 数据转换工具函数。

处理 SAP 返回数据中的常见格式问题：
- 物料编号前导零
- 日期格式转换
- 数值类型转换
- 超长文本截断
"""

from typing import Optional, Any, List, Dict
from datetime import datetime, date


def clean_material_no(matnr: Optional[str]) -> str:
    """清理物料编号前导零。SAP 物料编号常以 18 位定长返回，带前导零。"""
    if not matnr:
        return ''
    return matnr.lstrip('0') or matnr


def clean_leading_zeros(value: Optional[str]) -> str:
    """通用去前导零"""
    if not value:
        return ''
    return value.lstrip('0') or value


def sap_date_to_str(sap_date: Optional[str]) -> Optional[str]:
    """
    SAP 日期格式转换: YYYYMMDD → YYYY-MM-DD
    如 '20240603' → '2024-06-03'
    """
    if not sap_date or sap_date == '00000000':
        return None
    try:
        return f"{sap_date[:4]}-{sap_date[4:6]}-{sap_date[6:8]}"
    except (ValueError, IndexError):
        return sap_date


def sap_date_to_date(sap_date: Optional[str]) -> Optional[date]:
    """SAP 日期 → Python date 对象"""
    if not sap_date or sap_date == '00000000':
        return None
    try:
        return date(int(sap_date[:4]), int(sap_date[4:6]), int(sap_date[6:8]))
    except (ValueError, IndexError):
        return None


def sap_decimal(value: Optional[str]) -> Optional[float]:
    """
    SAP 数值字符串 → float。SAP 常用 CHAR 类型传数值。
    如 '1234.56' → 1234.56, '1000' → 1000.0
    """
    if value is None or value == '':
        return None
    try:
        return float(value.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None


def truncate_text(text: Optional[str], max_len: int = 50) -> str:
    """截断超长文本（保留前 max_len-2 字符 + '..'）"""
    if not text:
        return ''
    if len(text) <= max_len:
        return text
    return text[:max_len - 2] + '..'


def map_fields(record: Dict[str, Any], field_map: Dict[str, str]) -> Dict[str, Any]:
    """
    按字段映射表重命名字典键。
    field_map: {sap_field_name: python_field_name}
    未在映射表中的字段保持原样。
    """
    if not field_map:
        return record
    return {field_map.get(k, k): v for k, v in record.items()}


def parse_result_table(
    result: Dict[str, Any],
    table_name: str,
    field_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    从 RFC 返回结果中提取指定表并执行字段映射。

    Args:
        result: conn.call() 返回的原始字典
        table_name: 表名，如 'ZMARC', 'IT_OUTPUT', 'TB_KNA1'
        field_map: 可选，{SAP字段名: Python字段名} 映射

    Returns:
        记录列表（已映射字段名）
    """
    records = result.get(table_name, [])
    if field_map:
        records = [map_fields(r, field_map) for r in records]
    return records
