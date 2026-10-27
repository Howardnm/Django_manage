"""
app_sap_services.definitions — RFC 函数声明式定义。

每个文件对应一个业务域，包含该域的 RFC Schema 声明。
后期按需添加新文件/新 RFC，模式参考 material.py。

目录:
    material.py  — 物料主数据 (ZRFC_MATERIAL_MESN, ZFG_CHECK_MATERIAL)
    price.py     — 物料价格历史 (ZRFC_GET_MBEWH)
    vendor.py    — 供应商 (ZFG_CHECK_VENDOR)
    bom.py       — 成品材料 BOM (ZRFC_GET_MATERIAL_BOM, ZRFC_BOM_CREATE_FOR_PLM, ZFG_GET_MAST, ZRFC_DELETE_MATERIAL_BOM)
    # customer.py  — 客户主数据 (待添加)
    # sales.py     — 销售订单 (待添加)
    # ... 按需扩展
"""

from .material import MaterialQuery
from .price import MaterialPriceQuery
from .stock import MaterialStockQuery
from .vendor import VendorCheckQuery
from .bom import (
    MaterialBomQuery,
    MaterialBomMaintain,
    MaterialBomLinkQuery,
    MaterialBomDelete,
)

__all__ = [
    "MaterialQuery",
    "MaterialPriceQuery",
    "MaterialStockQuery",
    "VendorCheckQuery",
    "MaterialBomQuery",
    "MaterialBomMaintain",
    "MaterialBomLinkQuery",
    "MaterialBomDelete",
]
