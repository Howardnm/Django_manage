"""
app_sap_services.schemas — RFC Schema 声明式定义系统。

提供:
- RfcSchema: RFC 函数基类（元类自动收集参数/输出声明）
- RangeTableParam: SAP Range Table 参数描述符（支持 structure= 嵌套在 Import 结构内）
- ImportParam: 标量导入参数
- TableInput: 表输入参数
- OutputTable: 输出表声明基类
- SapMessage: SAP 业务消息（E_RTYPE/E_RTMSG）的识别与分级
- 字段类型: CharField, IntField, DecimalField, DateField, BoolField
"""

from .base import RfcSchema, RfcSchemaMeta
from .params import RangeTableParam, ImportParam, TableInput
from .outputs import OutputTable, OutputRecord
from .messages import SapMessage, normalize_type
from .fields import (
    Field,
    CharField,
    IntField,
    DecimalField,
    DateField,
    BoolField,
)

__all__ = [
    # 基类
    "RfcSchema",
    "RfcSchemaMeta",
    # 参数
    "RangeTableParam",
    "ImportParam",
    "TableInput",
    # 输出
    "OutputTable",
    "OutputRecord",
    # 消息
    "SapMessage",
    "normalize_type",
    # 字段
    "Field",
    "CharField",
    "IntField",
    "DecimalField",
    "DateField",
    "BoolField",
]
