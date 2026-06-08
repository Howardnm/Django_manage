"""
价格查询 SAP 服务。

已实现 RFC:
- ZRFC_GET_MBEW              — 读取物料评估价格
- ZRFC_GET_LAST_INVOICE_PRICE — 读取最新开票价格和最近交货时间
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class PriceService(BaseSAPService):
    """
    价格查询服务。

    使用示例:
        from app_sap_services import sap_price

        price = sap_price.get_material_valuation('A01001000003', plant='1010')
        last_price = sap_price.get_last_invoice_price('A01001000003')
    """

    # ==================================================================
    # ZRFC_GET_MBEW — 读取物料评估价格
    # ==================================================================

    def get_material_valuation(
        self,
        material_nr: str,
        plant: Optional[str] = None,
        valuation_area: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取物料评估价格 (RFC: ZRFC_GET_MBEW)。

        Args:
            material_nr: 物料编号
            plant: 工厂代码，如 '1010' = 广东顺采
            valuation_area: 评估范围 (BWKEY)

        Returns:
            list[dict]: 物料评估价格数据
        """
        table_params = {}

        table_params['S_MATNR'] = [self.build_range(
            'I', 'EQ', material_nr,
        )]

        if plant:
            table_params['S_WERKS'] = [self.build_range('I', 'EQ', plant)]

        if valuation_area:
            table_params['S_BWKEY'] = [self.build_range('I', 'EQ', valuation_area)]

        result = self._call_rfc('ZRFC_GET_MBEW', **table_params)
        return self.parse_result(result, 'IT_OUTPUT')

    # ==================================================================
    # ZRFC_GET_LAST_INVOICE_PRICE — 读取最新开票价格
    # ==================================================================

    def get_last_invoice_price(
        self,
        material_nr: str,
        customer_nr: Optional[str] = None,
        sales_org: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取最新的开票价格和最近的交货时间 (RFC: ZRFC_GET_LAST_INVOICE_PRICE)。

        Args:
            material_nr: 物料编号
            customer_nr: 客户编号（可选，查询指定客户的最近价格）
            sales_org:   销售组织

        Returns:
            list[dict]: 最近开票价格和交货时间
        """
        table_params = {}

        table_params['S_MATNR'] = [self.build_range('I', 'EQ', material_nr)]

        if customer_nr:
            table_params['S_KUNNR'] = [self.build_range('I', 'EQ', customer_nr)]

        if sales_org:
            table_params['S_VKORG'] = [self.build_range('I', 'EQ', sales_org)]

        result = self._call_rfc('ZRFC_GET_LAST_INVOICE_PRICE', **table_params)
        return self.parse_result(result, 'IT_OUTPUT')
