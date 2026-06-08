"""
外向交货单 SAP 服务。

已实现 RFC:
- ZRFC_CREATE_OUTB_DELIVERY — 创建外向交货单
- ZRFC_UPDATE_OUTB_DELIVERY — 修改外向交货单
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class DeliveryService(BaseSAPService):
    """
    交货单服务。

    使用示例:
        from app_sap_services import sap_delivery

        result = sap_delivery.create_delivery({
            # 交货单数据，参考 SAP 接口文档
        })
    """

    # ==================================================================
    # ZRFC_CREATE_OUTB_DELIVERY — 创建外向交货单
    # ==================================================================

    def create_delivery(
        self,
        delivery_data: Dict,
    ) -> Dict:
        """
        创建外向交货单 (RFC: ZRFC_CREATE_OUTB_DELIVERY)。

        Args:
            delivery_data: 交货单数据字典，具体字段请参考 SAP 接口文档
                          主要包含:
                          - 销售订单号
                          - 行项目信息
                          - 交货数量
                          - 发货工厂等

        Returns:
            dict: SAP 返回结果（含交货单号）
        """
        return self._call_rfc('ZRFC_CREATE_OUTB_DELIVERY', **delivery_data)

    # ==================================================================
    # ZRFC_UPDATE_OUTB_DELIVERY — 修改外向交货单
    # ==================================================================

    def update_delivery(
        self,
        delivery_nr: str,
        update_data: Dict,
    ) -> Dict:
        """
        修改外向交货单 (RFC: ZRFC_UPDATE_OUTB_DELIVERY)。

        Args:
            delivery_nr: 交货单号
            update_data: 要更新的字段数据

        Returns:
            dict: SAP 返回结果
        """
        return self._call_rfc(
            'ZRFC_UPDATE_OUTB_DELIVERY',
            DELIVERY_NR=delivery_nr,
            **update_data,
        )
