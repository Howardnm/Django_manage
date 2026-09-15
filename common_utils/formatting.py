"""数值展示格式化 — 跨层复用的唯一实现。

`smart_decimal` 此前在 common_utils/serializers/compare.py（名为 `_fmt`）与
common_utils/templatetags/project_extras.py 各有一份逐字相同的拷贝，本模块是
两者合并后的唯一实现。

约定（两处消费方共同依赖，改动即为契约变更）：
    - 固定 2 位小数；若第 3 位非 0 则显示 3 位（BOM 百分比常见 3 位精度）
    - None → '-'（模板与对比表统一用淡色 '-' 表示空值）
    - 无法解析为数值时原样返回 str(value)，不抛异常（模板 filter 不能炸）

本模块保持零 Django 依赖，可被 MCP、管理命令、独立脚本复用。
"""

from decimal import Decimal


def smart_decimal(value):
    """强制 2 位小数；若第 3 位非 0 则显示 3 位。

    Args:
        value: Decimal / float / int / 数字字符串 / None
    Returns:
        str — 已格式化的展示字符串，空值为 '-'
    """
    if value is None:
        return '-'
    try:
        d = Decimal(str(value)).quantize(Decimal('0.001'))
    except Exception:
        return str(value)
    third = d.as_tuple().exponent  # e.g. -3 means 3 decimal places
    # 保留3位小数后，检查第3位是否为0
    if third == -3:
        # 第3位是否为0
        if d.as_tuple().digits[-1] == 0:
            return '{:.2f}'.format(d)
        else:
            return '{:.3f}'.format(d)
    # 不足3位，直接按2位显示
    return '{:.2f}'.format(d)
