"""
app_sap_services — SAP RFC 服务模块。

声明式、Schema 驱动的 SAP 数据访问层。新增 RFC 接口只需定义 RfcSchema 子类，
无需手写连接管理、参数构建、结果解析等重复代码。

用法:
    from app_sap_services import sap
    from app_sap_services.definitions.material import MaterialQuery

    # 链式调用
    result = sap.rfc(MaterialQuery) \
        .filter(mat_range__cp="A01*") \
        .filter(mta_range__eq="ROH") \
        .limit(50) \
        .call()

    # 快捷调用
    result = sap.call(MaterialQuery, mat_range__cp="A01*", mta_range__eq="ROH")

    for row in result:
        print(row.MATNR, row.MAKTX, row.MTART)

    # 原始调用（未声明 Schema 的临时调试）
    result = sap.execute_raw("ZRFC_MATERIAL_MESN", MAT_RANGE=[...])

架构:
    schemas/     — RFC Schema 定义系统 (RfcSchema, RangeTableParam, OutputTable, fields)
    query/       — 查询引擎 (SAPGateway, RfcQuery)
    definitions/ — RFC 函数声明式定义 (按业务域分文件)
    config.py    — SAPConfig 配置
    connection.py— ConnectionManager 线程安全连接池
    converters.py— SAP 数据转换工具函数
    exceptions.py— 异常层次结构
"""

import threading

from .exceptions import (
    SAPError,
    SAPConfigError,
    SAPConnectionError,
    SAPRfcError,
    SAPFilterError,
    SAPResultParseError,
    DoesNotExist,
    MultipleObjectsReturned,
)
from .config import SAPConfig
from .query.gateway import SAPGateway, _get_gateway

__all__ = [
    # 入口
    "sap",
    "sap_health_check",
    # 异常
    "SAPError",
    "SAPConfigError",
    "SAPConnectionError",
    "SAPRfcError",
    "SAPFilterError",
    "SAPResultParseError",
    "DoesNotExist",
    "MultipleObjectsReturned",
    # 配置
    "SAPConfig",
    "SAPGateway",
]


# =============================================================================
# 惰性代理：sap.xxx 首次访问时自动委托给 _get_gateway()（其内部已线程安全）
# =============================================================================

class _LazyGateway:
    """
    惰性代理：首次访问属性时委托给 _get_gateway()。

    不自行加锁，线程安全由 _get_gateway() 的双检锁保证。
    """

    def __getattr__(self, name):
        return getattr(_get_gateway(), name)


sap = _LazyGateway()


def sap_health_check() -> dict:
    """SAP 连接健康检查（延迟初始化）"""
    return sap.health_check()
