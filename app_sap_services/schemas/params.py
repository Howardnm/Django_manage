"""
SAP RFC 参数定义 — RangeTableParam / ImportParam / TableInput。

RangeTableParam 是核心：封装 SAP Range Table 的 SIGN/OPTION/LOW/HIGH 结构，
提供链式快捷方法直接构建筛选条件行。
"""

from typing import Any, Dict

# SAP OPTION → 人类可读说明
OPTION_LABELS = {
    "EQ": "等于",
    "NE": "不等于",
    "CP": "包含模式（支持 * 通配符）",
    "NP": "不包含模式",
    "BT": "介于（含边界）",
    "NB": "不介于",
    "GT": "大于",
    "LT": "小于",
    "GE": "大于等于",
    "LE": "小于等于",
}

# __op 后缀 → SAP OPTION 映射（base.py 引用此表，单一来源）
OP_SUFFIX_MAP = {
    "__eq": "EQ",
    "__ne": "NE",
    "__cp": "CP",
    "__np": "NP",
    "__bt": "BT",
    "__nb": "NB",
    "__gt": "GT",
    "__lt": "LT",
    "__ge": "GE",
    "__le": "LE",
}


class RangeTableParam:
    """
    SAP Range Table 参数描述符。

    封装一个 Range Table 参数名及其对应 SAP 字段的筛选能力。

    Args:
        rfc_name: RFC 函数中该 Range Table 的参数名，如 "MAT_RANGE"
        field: SAP 字段名，如 "MATNR"
        low_field: LOW 值的字段名，默认为 "LOW"（特殊表如 MTART 用 "MTART_LOW"）
        high_field: HIGH 值的字段名，默认为 "HIGH"

    使用示例:
        mat_range = RangeTableParam("MAT_RANGE", field="MATNR")

        # 在 RFC 定义中声明
        class MaterialQuery(RfcSchema):
            mat_range = RangeTableParam("MAT_RANGE", field="MATNR")

        # 调用时链式筛选
        MaterialQuery.call(mat_range__cp="A01*", mat_range__eq="B0200500001")
    """

    def __init__(
        self,
        rfc_name: str,
        field: str,
        low_field: str = "LOW",
        high_field: str = "HIGH",
    ):
        self.rfc_name = rfc_name
        self.field = field
        self.low_field = low_field
        self.high_field = high_field
        # 由 RfcSchema 元类设置
        self._attr_name = ""

    # ---- 链式构建方法（返回单行 range dict）----

    @staticmethod
    def _safe_str(value: Any) -> str:
        """安全转字符串：None → ''，0/'0'/False 保留"""
        if value is None:
            return ""
        return str(value)

    def eq(self, value: Any) -> Dict[str, str]:
        """【EQ】精确等于"""
        return self._row("I", "EQ", self._safe_str(value), "")

    def ne(self, value: Any) -> Dict[str, str]:
        """【NE】不等于"""
        return self._row("I", "NE", self._safe_str(value), "")

    def cp(self, pattern: str) -> Dict[str, str]:
        """【CP】包含模式匹配（支持 * 通配符）"""
        return self._row("I", "CP", self._safe_str(pattern), "")

    def np(self, pattern: str) -> Dict[str, str]:
        """【NP】不包含模式"""
        return self._row("I", "NP", self._safe_str(pattern), "")

    def bt(self, low: Any, high: Any) -> Dict[str, str]:
        """【BT】介于 low 和 high 之间（含边界）"""
        return self._row("I", "BT", self._safe_str(low), self._safe_str(high))

    def nb(self, low: Any, high: Any) -> Dict[str, str]:
        """【NB】不介于"""
        return self._row("I", "NB", self._safe_str(low), self._safe_str(high))

    def gt(self, value: Any) -> Dict[str, str]:
        """【GT】大于"""
        return self._row("I", "GT", self._safe_str(value), "")

    def ge(self, value: Any) -> Dict[str, str]:
        """【GE】大于等于"""
        return self._row("I", "GE", self._safe_str(value), "")

    def lt(self, value: Any) -> Dict[str, str]:
        """【LT】小于"""
        return self._row("I", "LT", self._safe_str(value), "")

    def le(self, value: Any) -> Dict[str, str]:
        """【LE】小于等于"""
        return self._row("I", "LE", self._safe_str(value), "")

    # ---- 排除条件 (SIGN='E') ----

    def exclude_eq(self, value: Any) -> Dict[str, str]:
        """排除精确等于"""
        return self._row("E", "EQ", self._safe_str(value), "")

    def exclude_ne(self, value: Any) -> Dict[str, str]:
        """排除不等于（即包含除该值外的所有值）"""
        return self._row("E", "NE", self._safe_str(value), "")

    def exclude_cp(self, pattern: str) -> Dict[str, str]:
        """排除匹配模式"""
        return self._row("E", "CP", self._safe_str(pattern), "")

    def exclude_np(self, pattern: str) -> Dict[str, str]:
        """排除不包含模式（即只包含匹配的值）"""
        return self._row("E", "NP", self._safe_str(pattern), "")

    def exclude_bt(self, low: Any, high: Any) -> Dict[str, str]:
        """排除介于 low 和 high 之间的值"""
        return self._row("E", "BT", self._safe_str(low), self._safe_str(high))

    def exclude_nb(self, low: Any, high: Any) -> Dict[str, str]:
        """排除不介于的值（即只包含介于 low 和 high 的值）"""
        return self._row("E", "NB", self._safe_str(low), self._safe_str(high))

    def exclude_gt(self, value: Any) -> Dict[str, str]:
        """排除大于某值的记录"""
        return self._row("E", "GT", self._safe_str(value), "")

    def exclude_ge(self, value: Any) -> Dict[str, str]:
        """排除大于等于某值的记录"""
        return self._row("E", "GE", self._safe_str(value), "")

    def exclude_lt(self, value: Any) -> Dict[str, str]:
        """排除小于某值的记录"""
        return self._row("E", "LT", self._safe_str(value), "")

    def exclude_le(self, value: Any) -> Dict[str, str]:
        """排除小于等于某值的记录"""
        return self._row("E", "LE", self._safe_str(value), "")

    def _row(self, sign: str, option: str, low: str, high: str) -> Dict[str, str]:
        """内部：构建单行 range 字典"""
        if self.low_field == "LOW" and self.high_field == "HIGH":
            return {"SIGN": sign, "OPTION": option, "LOW": low, "HIGH": high}
        else:
            return {
                "SIGN": sign,
                "OPTION": option,
                self.low_field: low,
                self.high_field: high,
            }

    def __repr__(self):
        return (
            f"RangeTableParam(rfc_name={self.rfc_name!r}, field={self.field!r}, "
            f"low={self.low_field!r}, high={self.high_field!r})"
        )


class ImportParam:
    """
    SAP Import（标量输入）参数描述符。

    Args:
        rfc_name: RFC 函数中的参数名，如 "IV_MATNR"

    使用示例:
        iv_matnr = ImportParam("IV_MATNR")

        # 构建参数
        params = {"IV_MATNR": "A01001000003"}
    """

    def __init__(self, rfc_name: str):
        self.rfc_name = rfc_name
        self._attr_name = ""

    def __repr__(self):
        return f"ImportParam(rfc_name={self.rfc_name!r})"


class TableInput:
    """
    SAP Tables（表输入）参数描述符。

    Args:
        rfc_name: RFC 函数中的表参数名，如 "IT_ITEM"
        schema: 可选的 OutputTable 子类，描述表结构（用于文档/验证）

    使用示例:
        items = TableInput("IT_ITEM")

        # 构建参数
        params = {"IT_ITEM": [{"WERKS": "1010", ...}]}
    """

    def __init__(self, rfc_name: str, schema=None):
        self.rfc_name = rfc_name
        self.schema = schema
        self._attr_name = ""

    def __repr__(self):
        return f"TableInput(rfc_name={self.rfc_name!r})"
