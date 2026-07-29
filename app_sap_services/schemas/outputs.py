"""
OutputTable — SAP 返回表的声明式定义。

用法:
    class ZMARC(OutputTable):
        MATNR = CharField("物料编号", converter=clean_leading_zeros)
        MAKTX = CharField("物料描述")

    # 解析 SAP 返回的原始 dict
    record = ZMARC.map_record({"MATNR": "000000A01001", "MAKTX": "PP"})
    print(record.MATNR)  # → "A01001"
"""

from typing import Any, Dict, List

from .fields import Field


class OutputRecord:
    """
    类型化的单条输出记录。

    支持:
    - 属性访问: record.MATNR
    - dict 访问: record["MATNR"]
    - repr 展示
    """

    __slots__ = ("_data",)

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        # NOTE: _data 通过 __slots__ 直接访问，不会触发 __getattr__
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(
                f"{self.__class__.__name__!r} 没有字段 {name!r}"
            ) from None

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default=None) -> Any:
        return self._data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """转为普通 dict"""
        return dict(self._data)

    def __repr__(self):
        items = ", ".join(f"{k}={v!r}" for k, v in list(self._data.items())[:6])
        more = "..." if len(self._data) > 6 else ""
        return f"{self.__class__.__name__}({items}{more})"


class OutputTableMeta(type):
    """OutputTable 元类：自动收集 Field 声明"""

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)

        # 跳过基础 OutputTable 类本身
        if name == "OutputTable":
            return cls

        # 收集字段
        fields: Dict[str, Field] = {}
        # 继承父类字段
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        # 当前类的字段
        for key, value in namespace.items():
            if isinstance(value, Field):
                value.sap_name = key
                fields[key] = value

        cls._fields = fields
        return cls


class OutputTable(metaclass=OutputTableMeta):
    """
    SAP 输出表描述符。

    在 RfcSchema 中作为内嵌类使用：
        class MyQuery(RfcSchema):
            class IT_OUTPUT(OutputTable):
                FIELD_A = CharField("字段A")
                FIELD_B = IntField("字段B")
    """

    _fields: Dict[str, Field] = {}

    # 每个 OutputTable 子类的记录类型缓存（避免重复创建类）
    _record_cls = None

    @classmethod
    def _get_record_cls(cls):
        """获取或创建该 OutputTable 对应的 OutputRecord 子类（缓存）"""
        if cls._record_cls is None:
            cls._record_cls = type(f"{cls.__name__}Record", (OutputRecord,), {})
        return cls._record_cls

    @classmethod
    def map_record(cls, raw: Dict[str, Any]) -> OutputRecord:
        """将 SAP 返回的原始 dict 转换为类型化 OutputRecord"""
        data = {}
        for sap_name, field in cls._fields.items():
            raw_value = raw.get(sap_name)
            data[sap_name] = field.convert(raw_value)
        return cls._get_record_cls()(data)

    @classmethod
    def map_records(cls, raw_list: List[Dict[str, Any]]) -> List[OutputRecord]:
        """批量转换 SAP 返回的原始记录列表"""
        return [cls.map_record(r) for r in raw_list]

    @classmethod
    def describe(cls) -> str:
        """返回字段说明（用于调试/文档）"""
        lines = [f"OutputTable: {cls.__name__}"]
        for name, field in cls._fields.items():
            lines.append(f"  {name}: {field.label or '(无说明)'}")
        return "\n".join(lines)
