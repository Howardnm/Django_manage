"""
app_sap_services.definitions — RFC 函数声明式定义。

每个文件对应一个业务域，包含该域的 RFC Schema 声明。
后期按需添加新文件/新 RFC，模式参考 material.py。

目录:
    material.py  — 物料主数据 (ZRFC_MATERIAL_MESN, ZFG_CHECK_MATERIAL)
    price.py     — 物料价格 (ZRFC_GET_MBEW)
    vendor.py    — 供应商 (ZFG_CHECK_VENDOR)
    # customer.py  — 客户主数据 (待添加)
    # sales.py     — 销售订单 (待添加)
    # ... 按需扩展
"""

from .material import MaterialQuery
from .price import MaterialPriceQuery
from .stock import MaterialStockQuery
from .vendor import VendorCheckQuery

__all__ = [
    "MaterialQuery",
    "MaterialPriceQuery",
    "MaterialStockQuery",
    "VendorCheckQuery",
]
