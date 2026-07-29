"""
app_sap_services.query — RFC 查询引擎。

提供:
- SAPGateway: 顶层入口（管理连接 + 提供 rfc()/call() 方法）
- RfcQuery: 链式查询 builder（.filter().limit().call()）
"""

from .gateway import SAPGateway, _get_gateway
from .builder import RfcQuery

__all__ = [
    "SAPGateway",
    "RfcQuery",
    "_get_gateway",
]
