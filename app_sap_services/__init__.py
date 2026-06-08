"""
app_sap_services — SAP RFC 服务模块。

提供统一的 SAP 数据访问层，供其他 Django app import 调用。
所有服务均为惰性初始化单例，首次调用时自动建立 SAP 连接。

用法:
    from app_sap_services import sap_material

    materials = sap_material.query_materials(mat_nr='A01*', mat_type='ROH')

可用服务:
    sap_material    — 物料主数据
    sap_customer    — 客户主数据
    sap_sales       — 销售订单
    sap_price       — 价格查询
    sap_delivery    — 交货单
    sap_production  — 生产工单/计件工资
    sap_vendor      — 供应商
    sap_wms         — 领料数据
    sap_quota       — 配额协议
"""

from .exceptions import (
    SAPError,
    SAPConfigError,
    SAPConnectionError,
    SAPRfcError,
    SAPFilterError,
    SAPResultParseError,
)
from .filters import SAPFilter
from .config import SAPConfig
from .connection import ConnectionManager

# 服务类
from .services.material import MaterialService
from .services.customer import CustomerService
from .services.sales import SalesService
from .services.price import PriceService
from .services.delivery import DeliveryService
from .services.production import ProductionService
from .services.vendor import VendorService
from .services.wms import WMSService
from .services.quota import QuotaService

__all__ = [
    # 异常
    'SAPError', 'SAPConfigError', 'SAPConnectionError',
    'SAPRfcError', 'SAPFilterError', 'SAPResultParseError',
    # 工具
    'SAPFilter', 'SAPConfig',
    # 服务单例
    'sap_material', 'sap_customer', 'sap_sales', 'sap_price',
    'sap_delivery', 'sap_production', 'sap_vendor', 'sap_wms', 'sap_quota',
    # 健康检查
    'sap_health_check',
]


# ======================================================================
# 惰性初始化：Django 启动时 settings 可能尚未加载，延迟到首次调用
# ======================================================================

_conn_manager: ConnectionManager = None
_service_cache: dict = {}


def _get_connection_manager() -> ConnectionManager:
    """获取全局连接管理器（惰性初始化）"""
    global _conn_manager
    if _conn_manager is None:
        config = SAPConfig.from_django_settings()
        _conn_manager = ConnectionManager(config)
    return _conn_manager


def _get_service(service_class):
    """获取服务单例（惰性初始化）"""
    if service_class not in _service_cache:
        _service_cache[service_class] = service_class(_get_connection_manager())
    return _service_cache[service_class]


# 对外暴露的惰性服务单例（通过模块级 __getattr__ 实现零开销惰性访问）
# Python 3.7+ 支持
def __getattr__(name):
    _services = {
        'sap_material': MaterialService,
        'sap_customer': CustomerService,
        'sap_sales': SalesService,
        'sap_price': PriceService,
        'sap_delivery': DeliveryService,
        'sap_production': ProductionService,
        'sap_vendor': VendorService,
        'sap_wms': WMSService,
        'sap_quota': QuotaService,
    }
    if name in _services:
        return _get_service(_services[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def sap_health_check() -> dict:
    """SAP 连接健康检查"""
    try:
        mgr = _get_connection_manager()
        return mgr.health_check()
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
