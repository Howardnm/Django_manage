"""
销售订单 SAP 服务。

已实现 RFC:
- ZRFC_GET_SALES_PRICE_LIST — 读取价格主数据
- ZRFC_GET_SALE_ORDERS     — 读取销售订单（抬头 + 行项目）
- ZRFC_CREATE_SALE_ORDERS  — 创建销售订单
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class SalesService(BaseSAPService):
    """
    销售订单服务。

    使用示例:
        from app_sap_services import sap_sales

        orders = sap_sales.get_sale_orders(material_nr='A01*')
    """

    # ==================================================================
    # ZRFC_GET_SALES_PRICE_LIST — 读取价格主数据
    # ==================================================================

    def get_price_list(
        self,
        material_nr: Optional[str] = None,
        customer_nr: Optional[str] = None,
        sales_org: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取价格主数据 (RFC: ZRFC_GET_SALES_PRICE_LIST)。

        Args:
            material_nr: 物料编号，支持通配符 *
            customer_nr: 客户编号
            sales_org:   销售组织 (如 '1010' = 广东顺采)

        Returns:
            list[dict]: 价格信息列表
        """
        table_params = {}

        if material_nr:
            option = 'CP' if '*' in material_nr else 'EQ'
            table_params['S_MATNR'] = [self.build_range('I', option, material_nr)]

        if customer_nr:
            option = 'CP' if '*' in customer_nr else 'EQ'
            table_params['S_KUNNR'] = [self.build_range('I', option, customer_nr)]

        if sales_org:
            table_params['S_VKORG'] = [self.build_range('I', 'EQ', sales_org)]

        result = self._call_rfc('ZRFC_GET_SALES_PRICE_LIST', **table_params)
        return self.parse_result(result, 'IT_OUTPUT')

    # ==================================================================
    # ZRFC_GET_SALE_ORDERS — 读取销售订单
    # ==================================================================

    def get_sale_orders(
        self,
        order_nr: Optional[str] = None,
        material_nr: Optional[str] = None,
        customer_nr: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, List[Dict]]:
        """
        读取销售订单，包含抬头和行项目 (RFC: ZRFC_GET_SALE_ORDERS)。

        Args:
            order_nr:    销售订单号 (VBELN)，如 '0000100001'
            material_nr: 物料编号，支持通配符 *
            customer_nr: 客户编号 (KUNNR)
            date_from:   创建日期-起始 (YYYYMMDD)
            date_to:     创建日期-截止 (YYYYMMDD)

        Returns:
            dict: 含抬头表 (HEADER) 和行项目表 (ITEMS)
        """
        table_params = {}

        if order_nr:
            option = 'CP' if '*' in order_nr else 'EQ'
            table_params['S_VBELN'] = [self.build_range('I', option, order_nr)]

        if material_nr:
            option = 'CP' if '*' in material_nr else 'EQ'
            table_params['S_MATNR'] = [self.build_range('I', option, material_nr)]

        if customer_nr:
            option = 'CP' if '*' in customer_nr else 'EQ'
            table_params['S_KUNNR'] = [self.build_range('I', option, customer_nr)]

        if date_from or date_to:
            option = 'BT' if (date_from and date_to) else ('GE' if date_from else 'LE')
            table_params['S_ERDAT'] = [self.build_range(
                'I', option, date_from or '', date_to or ''
            )]

        return self._call_rfc('ZRFC_GET_SALE_ORDERS', **table_params)

    # ==================================================================
    # ZRFC_CREATE_SALE_ORDERS — 创建销售订单
    # ==================================================================

    def create_sale_orders(
        self,
        order_data: Dict,
    ) -> Dict:
        """
        创建销售订单 (RFC: ZRFC_CREATE_SALE_ORDERS)。

        Args:
            order_data: 订单数据字典，具体字段请参考 SAP 接口文档

        Returns:
            dict: SAP 返回结果（含订单号等信息）
        """
        return self._call_rfc('ZRFC_CREATE_SALE_ORDERS', **order_data)
