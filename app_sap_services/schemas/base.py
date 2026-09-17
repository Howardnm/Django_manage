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
import logging

from ..converters import safe_str
from ..exceptions import SAPBusinessError

from .messages import SapMessage, normalize_type, WARN_TYPES
from .params import RangeTableParam, ImportParam, TableInput, OP_SUFFIX_MAP
from .outputs import OutputTable

logger = logging.getLogger("sap.schema")


class RfcSchemaMeta(type):
    """
    RfcSchema 元类。

    自动遍历类属性，收集:
    - _range_params: {attr_name → RangeTableParam}
    - _import_params: {attr_name → ImportParam}
    - _table_inputs: {attr_name → TableInput}
    - _output_tables: {inner_class_name → OutputTable class}
    - _structures: {结构名 → [描述符, ...]}（声明了 structure= 的参数按归属分组）
    """

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)

        if name == "RfcSchema" and cls.__module__ == __name__:
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

        # 按 structure 分组，供 build_params 定位嵌套容器
        structures: Dict[str, list] = {}
        for p in list(range_params.values()) + list(import_params.values()):
            if getattr(p, "structure", None):
                structures.setdefault(p.structure, []).append(p)
        cls._structures = structures

        # 验证 1：结构名不得与顶层参数重名，否则写入时会互相覆盖
        top_level_names = (
            {p.rfc_name for p in range_params.values() if not p.structure}
            | {p.rfc_name for p in import_params.values() if not p.structure}
            | {p.rfc_name for p in table_inputs.values()}
        )
        for sname in structures:
            if sname in top_level_names:
                raise TypeError(
                    f"RfcSchema 子类 {name!r} 的 Import 结构名 {sname!r} "
                    f"与顶层 RFC 参数重名，组装参数时会互相覆盖。"
                )

        # 验证 2：子类必须定义 function_name
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

    # ---- 消息检查（默认关闭；声明后 parse_response 会自动检查）----
    # 典型用法（Z 开头 RFC 常带 E_RTYPE/E_RTMSG 这对 Export）:
    #     msg_type_field = "E_RTYPE"
    #     msg_text_field = "E_RTMSG"
    msg_type_field: ClassVar[str] = ""
    msg_text_field: ClassVar[str] = ""

    # 这些消息文本表示「本次查询没有数据」，属正常空结果而非业务错误。
    # 部分 Z 开头 RFC 用 E 级 + 特定文本表达「查无数据」（如 ZRFC_GET_MBEWH
    # 返回 '未查询到数据'），若一律当错误，会让「该物料没有价格」这种正常
    # 情况中断整个调用方流程。
    # 只能用文本区分 —— 真实错误（如无授权）同样返回 0 行，行数无法作为判据。
    msg_empty_texts: ClassVar[tuple] = ()

    _range_params: ClassVar[Dict[str, RangeTableParam]] = {}
    _import_params: ClassVar[Dict[str, ImportParam]] = {}
    _table_inputs: ClassVar[Dict[str, TableInput]] = {}
    _output_tables: ClassVar[Dict[str, Type[OutputTable]]] = {}
    _structures: ClassVar[Dict[str, list]] = {}

    @classmethod
    def build_params(cls, **kwargs) -> Dict[str, Any]:
        """
        将 filter(**kwargs) 传入的参数转换为 pyrfc 调用参数字典。

        支持的 kwargs 格式:
            param__op=value  → 对应 RangeTableParam
              如: mat_range__cp="A01*"  → MAT_RANGE: [{"SIGN":"I","OPTION":"CP","LOW":"A01*","HIGH":""}]
            iv_xxx=value      → 对应 ImportParam
            it_xxx=[...]      → 对应 TableInput

        声明了 structure 的参数会被写入嵌套 dict 而非顶层：
            s_matnr__cp="A01*"  → IS_QUERY: {"S_MATNR": [{"SIGN":"I","OPTION":"CP",...}]}

        Returns:
            dict: 可直接传给 conn.call(function_name, **result) 的参数字典
        """
        params: Dict[str, Any] = {}

        # 构建 attr_name → rfc_name 的映射
        range_attr_to_rfc = {p._attr_name: p for p in cls._range_params.values()}
        import_attr_to_rfc = {p._attr_name: p for p in cls._import_params.values()}
        table_attr_to_rfc = {p._attr_name: p for p in cls._table_inputs.values()}

        def _target(structure: str | None) -> Dict[str, Any]:
            """参数应写入的容器：顶层 params，或 params[structure] 这个嵌套 dict。"""
            if not structure:
                return params
            return params.setdefault(structure, {})

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
                    _target(rp.structure).setdefault(rp.rfc_name, []).append(row)
                    matched = True
                    break

            if matched:
                continue

            # 尝试匹配 ImportParam
            if key in import_attr_to_rfc:
                ip = import_attr_to_rfc[key]
                _target(ip.structure)[ip.rfc_name] = value
                matched = True

            # 尝试匹配 TableInput（表输入始终是顶层参数）
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

    @classmethod
    def _range_rows(cls, params: Dict[str, Any], rp: RangeTableParam) -> List[Dict[str, str]]:
        """
        取出某个 RangeTableParam 在 params 里的条件行列表。

        统一处理顶层与嵌套结构两种归属，供 builder 的 exclude 处理、
        describe() 与测试复用 —— 避免各处重复实现「假设 range 在顶层」的逻辑。

        Args:
            params: build_params 的产物
            rp: 目标 RangeTableParam

        Returns:
            条件行列表；不存在时返回空列表
        """
        container = params.get(rp.structure) if rp.structure else params
        if not isinstance(container, dict):
            return []
        rows = container.get(rp.rfc_name)
        return rows if isinstance(rows, list) else []

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
                low, high = safe_str(value[0]), safe_str(value[1])
            else:
                raise ValueError(
                    f"{rp._attr_name}{{__bt|__nb}} 需要 (low, high) 二元组，收到: {value!r}"
                )
        else:
            low = safe_str(value)
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
    def extract_messages(cls, raw_response: Dict[str, Any]) -> List[SapMessage]:
        """
        从 RFC 原始返回中抽取业务消息。

        只读 raw_response，不依赖解析结果 —— 因此可以在类型化之前调用。
        未声明 msg_type_field / msg_text_field 时始终返回空列表。

        Args:
            raw_response: conn.call() 返回的原始字典

        Returns:
            List[SapMessage]，按「标量消息 → 表消息」顺序
        """
        messages: List[SapMessage] = []

        if cls.msg_type_field:
            mtype = normalize_type(raw_response.get(cls.msg_type_field))
            text = str(raw_response.get(cls.msg_text_field) or "").strip()
            if mtype or text:
                messages.append(SapMessage(mtype, text, cls.msg_type_field))

        return messages

    @classmethod
    def is_empty_result_message(cls, message: SapMessage) -> bool:
        """该消息是否表示「查询无数据」（由 msg_empty_texts 声明）。"""
        if not message.text or not cls.msg_empty_texts:
            return False
        return message.text.strip() in cls.msg_empty_texts

    @classmethod
    def check_messages(cls, raw_response: Dict[str, Any]) -> List[SapMessage]:
        """
        检查 RFC 返回的业务消息，E（错误）/ A（终止）级时抛出 SAPBusinessError。

        S（成功）/ I（信息）/ 空值 / 字段缺失均视为正常 —— 大量 RFC 成功时
        返回的是空串，把「没有消息」当成失败会让同步整体误报。

        文本命中 msg_empty_texts 的消息视为「查询无数据」，不算错误。

        Args:
            raw_response: conn.call() 返回的原始字典

        Returns:
            全部消息（含被记日志的警告级）

        Raises:
            SAPBusinessError: 存在 E / A 级、且不属于空结果的消息时
        """
        if not cls.msg_type_field:
            return []

        messages = cls.extract_messages(raw_response)

        for m in messages:
            if m.type in WARN_TYPES:
                logger.warning("[%s] SAP 警告: %s", cls.function_name, m.text)

        fatal = [
            m for m in messages
            if m.is_fatal and not cls.is_empty_result_message(m)
        ]
        if fatal:
            raise SAPBusinessError(cls.function_name, fatal)

        return messages

    @classmethod
    def parse_response(
        cls,
        raw_response: Dict[str, Any],
        check: bool = True,
    ) -> Dict[str, List]:
        """
        解析 SAP RFC 返回的原始 dict，将输出表转换为类型化记录。

        声明了 msg_type_field 的 Schema 会先做业务消息检查（check=True 时），
        E / A 级消息抛 SAPBusinessError，避免「SAP 报错」被上层误认为「无数据」。
        诊断 / 回放场景可传 check=False 跳过。

        Args:
            raw_response: conn.call() 返回的原始字典
            check: 是否检查业务消息（默认 True）

        Returns:
            dict: {table_name: [OutputRecord, ...] 或原始值}

        Raises:
            SAPBusinessError: check=True 且 SAP 返回 E / A 级消息时
        """
        if check:
            cls.check_messages(raw_response)

        result = {}
        for key, value in raw_response.items():
            # 检查是否匹配已声明的输出表
            if key in cls._output_tables and isinstance(value, list):
                output_cls = cls._output_tables[key]
                result[key] = output_cls.map_records(value)
            elif key in cls._output_tables and isinstance(value, dict):
                # 单结构 Export（如校验类函数的 ES_LFA1）→ 类型化单条记录
                result[key] = cls._output_tables[key].map_record(value)
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
                path = f"{rp.structure}.{rp.rfc_name}" if rp.structure else rp.rfc_name
                lines.append(f"    {name} → {path} (field={rp.field})")

        if cls._import_params:
            lines.append("  Import 参数:")
            for name, ip in cls._import_params.items():
                path = f"{ip.structure}.{ip.rfc_name}" if ip.structure else ip.rfc_name
                lines.append(f"    {name} → {path}")

        if cls._table_inputs:
            lines.append("  Table 输入参数:")
            for name, ti in cls._table_inputs.items():
                lines.append(f"    {name} → {ti.rfc_name}")

        if cls._structures:
            lines.append("  嵌套 Import 结构:")
            for sname, members in cls._structures.items():
                lines.append(
                    f"    {sname}: " + ", ".join(p.rfc_name for p in members)
                )

        if cls.msg_type_field:
            lines.append(
                f"  消息检查: {cls.msg_type_field} / {cls.msg_text_field}"
                f" (E/A 级抛 SAPBusinessError)"
            )
            if cls.msg_empty_texts:
                lines.append(
                    f"    视为空结果(不抛错)的文本: {list(cls.msg_empty_texts)}"
                )

        if cls._output_tables:
            lines.append("  输出表:")
            for tname, tcls in cls._output_tables.items():
                field_list = ", ".join(tcls._fields.keys())
                lines.append(f"    {tname}: {field_list}")

        return "\n".join(lines)
