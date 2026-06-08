"""
WMS 仓库管理 SAP 服务。

已实现 RFC:
- ZRFC_GET_MAT_ORDER_ISSUE_DATA — 按物料查所有关联工单的领料数据
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class WMSService(BaseSAPService):
    """
    仓库管理 / 领料数据服务。

    使用示例:
        from app_sap_services import sap_wms

        records = sap_wms.get_material_order_issue_data(
            material_nr='A01001000003',
            plant='1010',
        )
    """

    # ==================================================================
    # ZRFC_GET_MAT_ORDER_ISSUE_DATA — 领料数据查询
    # ==================================================================

    def get_material_order_issue_data(
        self,
        material_nr: str,
        plant: Optional[str] = None,
        filter_teco: Optional[str] = None,
    ) -> List[Dict]:
        """
        按物料查所有关联工单的领料数据 (RFC: ZRFC_GET_MAT_ORDER_ISSUE_DATA)。

        Args:
            material_nr: 物料编号 (必填)
            plant: 工厂代码
                   - '1010' = 广东顺采
                   - '2010' = 佛山顺采
            filter_teco: 是否过滤已关闭工单
                         - 'X' = 排除已关闭(TECO)的工单
                         - ''  = 包含所有工单

        Returns:
            list[dict]: 领料数据列表，每条记录包含:
                AUFNR — 工单号
                MATNR — 物料编号
                WERKS — 工厂
                MEINS — 单位
                BDMNG — 需求数量
                ENMNG — 已发数量
        """
        import_params = {'IV_MATNR': material_nr}

        if plant:
            import_params['IV_WERKS'] = plant

        if filter_teco:
            import_params['IV_FILTER_TECO'] = filter_teco

        result = self._call_rfc('ZRFC_GET_MAT_ORDER_ISSUE_DATA', **import_params)
        return self.parse_result(result, 'IT_OUTPUT')
