"""SAP 物料主数据相关 RFC 调用"""

import logging

from .base import SapBaseService
from ..utils.converters import sap_date_to_python, sap_decimal_to_float

logger = logging.getLogger('app_sap_services')


class SapMaterialService(SapBaseService):
    """物料主数据 RFM 接口"""

    # ── 物料基础信息 ────────────────────────────────────────

    def get_material_detail(self, material_code: str) -> dict | None:
        """
        查询单个物料的基本信息。
        返回 None 表示物料不存在。
        """
        try:
            result = self._call_rfc(
                'BAPI_MATERIAL_GET_DETAIL',
                MATERIAL=material_code,
            )
            return result.get('MATERIAL_GENERAL_DATA', None)
        except Exception:
            logger.warning(f"查询物料 {material_code} 失败", exc_info=True)
            return None

    def search_materials(self, material_codes: list[str]) -> list[dict]:
        """批量查询物料信息"""
        if not material_codes:
            return []
        results = []
        for code in material_codes:
            detail = self.get_material_detail(code)
            if detail:
                results.append(detail)
        return results

    # ── 物料库存 ──────────────────────────────────────────

    def get_stock(self, material_code: str, plant: str = None,
                  storage_location: str = None) -> list[dict]:
        """
        查询物料库存信息。
        """
        params = {'MATERIAL': material_code}
        if plant:
            params['PLANT'] = plant
        if storage_location:
            params['STG_LOC'] = storage_location
        try:
            result = self._call_rfc('BAPI_MATERIAL_AVAILABILITY', **params)
            return result.get('STOCK_TABLE', [])
        except Exception:
            logger.warning(f"查询物料 {material_code} 库存失败", exc_info=True)
            return []

    # ── 物料价格 ──────────────────────────────────────────

    def get_price(self, material_code: str, plant: str = None) -> dict | None:
        """查询物料的标准价格"""
        params = {'MATERIAL': material_code}
        if plant:
            params['PLANT'] = plant
        try:
            result = self._call_rfc('BAPI_MATERIAL_GET_PRICE', **params)
            price_data = result.get('PRICE_DATA', {})
            if price_data:
                return {
                    'price': sap_decimal_to_float(price_data.get('PRICE', '0')),
                    'currency': price_data.get('CURRENCY', 'CNY'),
                    'price_unit': price_data.get('PRICE_UNIT', '1'),
                }
            return None
        except Exception:
            logger.warning(f"查询物料 {material_code} 价格失败", exc_info=True)
            return None
