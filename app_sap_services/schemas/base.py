"""
RfcSchema — RFC 函数声明式定义的基类。

每个 SAP RFC 函数通过继承此类来声明:
- function_name: RFC 函数名
- RangeTableParam 参数: 筛选条件参数
- ImportParam 参数: 标量导入参数
- TableInput 参数: 表输入参数
- OutputTable 内嵌类: 输出表结构

元类自动收集所有声明，提供 build_params / parse_response / call 方法。
"""

from typing import Any, Dict, List, Type, ClassVar

from .params import RangeTableParam, ImportParam, TableInput, OP_SUFFIX_MAP
from .outputs import OutputTable


class RfcSchemaMeta(type):
    """
    RfcSchema 元类。

    自动遍历类属性，收集:
    - _range_params: {attr_name → RangeTableParam}
    - _import_params: {attr_name → ImportParam}
    - _table_inputs: {attr_name → TableInput}
    - _output_tables: {inner_class_name → OutputTable class}
    """

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)

        if name == "RfcSchema":
            return cls

        # 继承基类已收集的参数
        range_params: Dict[str, RangeTableParam] = {}
        import_params: Dict[str, ImportParam] = {}
        table_inputs: Dict[str, TableInput] = {}
        output_tables: Dict[str, Type[OutputTable]] = {}

        for base in bases:
            if hasattr(base, "_range_params"):
                range_params.update(base._range_params)
            if hasattr(base, "_import_params"):
                import_params.update(base._import_params)
            if hasattr(base, "_table_inputs"):
                table_inputs.update(base._table_inputs)
            if hasattr(base, "_output_tables"):
                output_tables.update(base._output_tables)

        # 收集当前类的参数
        for key, value in namespace.items():
            if isinstance(value, RangeTableParam):
                value._attr_name = key
                range_params[key] = value
            elif isinstance(value, ImportParam):
                value._attr_name = key
                import_params[key] = value
            elif isinstance(value, TableInput):
                value._attr_name = key
                table_inputs[key] = value
            elif isinstance(value, type) and issubclass(value, OutputTable) and value is not OutputTable:
                output_tables[value.__name__] = value

        cls._range_params = range_params
        cls._import_params = import_params
        cls._table_inputs = table_inputs
        cls._output_tables = output_tables

        # 验证：子类必须定义 function_name
        if not cls.function_name:
            raise TypeError(
                f"RfcSchema 子类 {name!r} 必须定义 function_name 类属性。\n"
                f"示例: function_name = 'ZRFC_XXX'"
            )

        return cls


class RfcSchema(metaclass=RfcSchemaMeta):
    """
    RFC 函数声明式定义基类。

    子类需定义:
        function_name: str — RFC 函数名

    可选定义:
        0~N 个 RangeTableParam 实例 — 筛选条件参数
        0~N 个 ImportParam 实例 — 标量导入参数
        0~N 个 TableInput 实例 — 表输入参数
        0~N 个 OutputTable 内嵌类 — 输出表结构

    使用示例:
        class MaterialQuery(RfcSchema):
            function_name = "ZRFC_MATERIAL_MESN"

            mat_range = RangeTableParam("MAT_RANGE", field="MATNR")
            mta_range = RangeTableParam("MTA_RANGE", field="MTART",
                                         low_field="MTART_LOW", high_field="MTART_HIGH")

            class ZMARC(OutputTable):
                MATNR = CharField("物料编号", converter=clean_leading_zeros)
                MAKTX = CharField("物料描述")

        # 调用
        result = MaterialQuery.call(mat_range__cp="A01*", mta_range__eq="ROH")
    """

    function_name: ClassVar[str] = ""

    _range_params: ClassVar[Dict[str, RangeTableParam]] = {}
    _import_params: ClassVar[Dict[str, ImportParam]] = {}
    _table_inputs: ClassVar[Dict[str, TableInput]] = {}
    _output_tables: ClassVar[Dict[str, Type[OutputTable]]] = {}

    @classmethod
    def build_params(cls, **kwargs) -> Dict[str, Any]:
        """
        将 filter(**kwargs) 传入的参数转换为 pyrfc 调用参数字典。

        支持的 kwargs 格式:
            param__op=value  → 对应 RangeTableParam
              如: mat_range__cp="A01*"  → MAT_RANGE: [{"SIGN":"I","OPTION":"CP","LOW":"A01*","HIGH":""}]
            iv_xxx=value      → 对应 ImportParam
            it_xxx=[...]      → 对应 TableInput

        Returns:
            dict: 可直接传给 conn.call(function_name, **result) 的参数字典
        """
        params: Dict[str, Any] = {}

        # 构建 attr_name → rfc_name 的映射
        range_attr_to_rfc = {p._attr_name: p for p in cls._range_params.values()}
        import_attr_to_rfc = {p._attr_name: p for p in cls._import_params.values()}
        table_attr_to_rfc = {p._attr_name: p for p in cls._table_inputs.values()}

        for key, value in kwargs.items():
            matched = False

            # 尝试匹配 param__op 格式（RangeTableParam）
            for op_suffix, sap_option in OP_SUFFIX_MAP.items():
                if key.endswith(op_suffix):
                    attr_name = key[: -len(op_suffix)]
                    rp = range_attr_to_rfc.get(attr_name)
                    if rp is None:
                        raise ValueError(
                            f"未知的 RangeTableParam: {attr_name!r}，"
                            f"可用: {list(range_attr_to_rfc.keys())}"
                        )

                    # 构建 range table 行
                    row = cls._make_range_row(rp, sap_option, value)
                    params.setdefault(rp.rfc_name, []).append(row)
                    matched = True
                    break

            if matched:
                continue

            # 尝试匹配 ImportParam
            if key in import_attr_to_rfc:
                ip = import_attr_to_rfc[key]
                params[ip.rfc_name] = value
                matched = True

            # 尝试匹配 TableInput
            if not matched and key in table_attr_to_rfc:
                ti = table_attr_to_rfc[key]
                params[ti.rfc_name] = value
                matched = True

            if not matched:
                raise ValueError(
                    f"未知参数: {key!r}。"
                    f"可用的 RangeTable: {list(range_attr_to_rfc.keys())}\n"
                    f"可用的 Import: {list(import_attr_to_rfc.keys())}\n"
                    f"可用的 Table: {list(table_attr_to_rfc.keys())}\n"
                    f"支持的 operator 后缀: {list(OP_SUFFIX_MAP.keys())}"
                )

        return params

    @staticmethod
    def _safe_str(value: Any) -> str:
        """安全转字符串：None → ''，0/False 保留原值"""
        if value is None:
            return ""
        return str(value)

    @classmethod
    def _make_range_row(
        cls,
        rp: RangeTableParam,
        option: str,
        value: Any,
        sign: str = "I",
    ) -> Dict[str, str]:
        """根据 RangeTableParam 和 option 构建一行 range table"""
        if option in ("BT", "NB"):
            # 期待传入 (low, high) 元组
            if isinstance(value, (tuple, list)) and len(value) == 2:
                low, high = cls._safe_str(value[0]), cls._safe_str(value[1])
            else:
                raise ValueError(
                    f"{rp._attr_name}{{__bt|__nb}} 需要 (low, high) 二元组，收到: {value!r}"
                )
        else:
            low = cls._safe_str(value)
            high = ""

        if rp.low_field == "LOW" and rp.high_field == "HIGH":
            return {"SIGN": sign, "OPTION": option, "LOW": low, "HIGH": high}
        else:
            return {
                "SIGN": sign,
                "OPTION": option,
                rp.low_field: low,
                rp.high_field: high,
            }

    @classmethod
    def parse_response(cls, raw_response: Dict[str, Any]) -> Dict[str, List]:
        """
        解析 SAP RFC 返回的原始 dict，将输出表转换为类型化记录。

        Args:
            raw_response: conn.call() 返回的原始字典

        Returns:
            dict: {table_name: [OutputRecord, ...] 或原始值}
        """
        result = {}
        for key, value in raw_response.items():
            # 检查是否匹配已声明的输出表
            if key in cls._output_tables and isinstance(value, list):
                output_cls = cls._output_tables[key]
                result[key] = output_cls.map_records(value)
            else:
                result[key] = value
        return result

    # call() 快捷入口在 SAPGateway 上，不在此处 ——
    # 使用: sap.call(MaterialQuery, mat_range__cp="A01*")

    @classmethod
    def describe(cls) -> str:
        """返回 RFC 函数的人类可读说明"""
        lines = [f"RFC: {cls.function_name}"]
        if cls.__doc__:
            lines.append(f"  说明: {cls.__doc__.strip()}")

        if cls._range_params:
            lines.append("  Range Table 参数:")
            for name, rp in cls._range_params.items():
                lines.append(f"    {name} → {rp.rfc_name} (field={rp.field})")

        if cls._import_params:
            lines.append("  Import 参数:")
            for name, ip in cls._import_params.items():
                lines.append(f"    {name} → {ip.rfc_name}")

        if cls._table_inputs:
            lines.append("  Table 输入参数:")
            for name, ti in cls._table_inputs.items():
                lines.append(f"    {name} → {ti.rfc_name}")

        if cls._output_tables:
            lines.append("  输出表:")
            for tname, tcls in cls._output_tables.items():
                field_list = ", ".join(tcls._fields.keys())
                lines.append(f"    {tname}: {field_list}")

        return "\n".join(lines)
