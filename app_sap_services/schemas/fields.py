"""
SAP 输出字段类型定义。

每个 Field 子类描述 SAP 返回表中的一个字段：
- 字段名自动从类属性名获取（SAP 原始字段名）
- 类型转换由 converter 参数处理
- label 提供中文说明（用于文档/调试）
"""

from typing import Any, Callable, Optional
from datetime import date, datetime


class Field:
    """输出字段基类"""

    def __init__(self, label: str = "", converter: Optional[Callable] = None):
        self.label = label
        self.converter = converter
        self.sap_name = ""  # 由 OutputTable 元类自动设置

    def convert(self, value: Any) -> Any:
        """将 SAP 原始值转换为 Python 类型"""
        if value is None:
            return None
        if self.converter:
            return self.converter(value)
        return value

    def __repr__(self):
        return f"{self.__class__.__name__}({self.sap_name!r}, label={self.label!r})"


class CharField(Field):
    """字符串字段。默认不做转换，可传入 converter 做后处理"""

    def convert(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        if self.converter:
            return self.converter(s)
        return s


class IntField(Field):
    """整数字段。SAP 常用 CHAR/NUMC 类型传数值"""

    def convert(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        if self.converter:
            value = self.converter(value)
        try:
            return int(value)
        except (ValueError, TypeError):
            return None


class DecimalField(Field):
    """定点数字段。SAP 常用 CHAR 类型传数值（如 '1234.56'）"""

    def __init__(self, label: str = "", decimals: int = 2, converter: Optional[Callable] = None):
        super().__init__(label, converter)
        self.decimals = decimals

    def convert(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if self.converter:
            value = self.converter(value)
        try:
            s = str(value).strip().replace(",", "")
            return round(float(s), self.decimals)
        except (ValueError, TypeError):
            return None


class DateField(Field):
    """日期字段。SAP 常用 YYYYMMDD 格式"""

    def __init__(self, label: str = "", fmt: str = "%Y%m%d", converter: Optional[Callable] = None):
        super().__init__(label, converter)
        self.fmt = fmt

    def convert(self, value: Any) -> Optional[date]:
        if value is None:
            return None
        if self.converter:
            value = self.converter(value)
        s = str(value).strip()
        if not s or s == "00000000":
            return None
        try:
            return datetime.strptime(s, self.fmt).date()
        except ValueError:
            return None


class BoolField(Field):
    """布尔字段。SAP 常用 CHAR1 类型，'X' = True, '' = False"""

    def convert(self, value: Any) -> Optional[bool]:
        if value is None:
            return None
        if self.converter:
            value = self.converter(value)
        s = str(value).strip().upper()
        return s in ("X", "TRUE", "1", "YES")
