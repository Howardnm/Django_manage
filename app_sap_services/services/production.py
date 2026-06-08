"""
计件工资 / 生产工单 SAP 服务。

已实现 RFC:
- ZIF_MES_GET_OPEN_PROD         — 读取未关闭的工单
- ZIF_MES_GET_MACHINE_DESCRIBE  — 读取机台描述
- ZIF_JJGZ_GET_ORDER_DATA       — 读取工单工序信息
- ZIF_JJGZ_CREATE_PRODORDCF     — 创建报工
- ZIF_JJGZ_CANCEL_PRODORDCF     — 取消报工
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class ProductionService(BaseSAPService):
    """
    生产工单 / 计件工资服务。

    使用示例:
        from app_sap_services import sap_production

        orders = sap_production.get_open_production_orders(plant='1010')
        machines = sap_production.get_machine_describe(plant='1010')
    """

    # ==================================================================
    # ZIF_MES_GET_OPEN_PROD — 读取未关闭的工单
    # ==================================================================

    def get_open_production_orders(
        self,
        plant: Optional[str] = None,
        order_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取未关闭的工单 (RFC: ZIF_MES_GET_OPEN_PROD)。

        Args:
            plant: 工厂代码
                   - '1010' = 广东顺采
                   - '2010' = 佛山顺采
            order_type: 订单类型筛选

        Returns:
            list[dict]: 未关闭工单列表
        """
        params = {}
        if plant:
            params['WERKS'] = plant
        if order_type:
            params['AUART'] = order_type

        result = self._call_rfc('ZIF_MES_GET_OPEN_PROD', **params)
        return self.parse_result(result, 'IT_OUTPUT')

    # ==================================================================
    # ZIF_MES_GET_MACHINE_DESCRIBE — 读取机台描述
    # ==================================================================

    def get_machine_describe(
        self,
        plant: Optional[str] = None,
        work_center: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取机台描述 (RFC: ZIF_MES_GET_MACHINE_DESCRIBE)。

        Args:
            plant: 工厂代码
            work_center: 工作中心编号

        Returns:
            list[dict]: 机台信息列表
        """
        params = {}
        if plant:
            params['WERKS'] = plant
        if work_center:
            params['ARBPL'] = work_center

        result = self._call_rfc('ZIF_MES_GET_MACHINE_DESCRIBE', **params)
        return self.parse_result(result, 'IT_OUTPUT')

    # ==================================================================
    # ZIF_JJGZ_GET_ORDER_DATA — 读取工单工序信息
    # ==================================================================

    def get_order_data(
        self,
        order_nr: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取工单工序信息 (RFC: ZIF_JJGZ_GET_ORDER_DATA)。

        Args:
            order_nr: 工单号

        Returns:
            list[dict]: 工单工序详细数据
        """
        params = {}
        if order_nr:
            params['AUFNR'] = order_nr

        result = self._call_rfc('ZIF_JJGZ_GET_ORDER_DATA', **params)
        return self.parse_result(result, 'IT_OUTPUT')

    # ==================================================================
    # ZIF_JJGZ_CREATE_PRODORDCF — 创建报工
    # ==================================================================

    def create_production_confirmation(
        self,
        confirmation_data: Dict,
    ) -> Dict:
        """
        创建报工 (RFC: ZIF_JJGZ_CREATE_PRODORDCF)。

        Args:
            confirmation_data: 报工数据字典，具体字段请参考 SAP 接口文档

        Returns:
            dict: SAP 返回结果
        """
        return self._call_rfc('ZIF_JJGZ_CREATE_PRODORDCF', **confirmation_data)

    # ==================================================================
    # ZIF_JJGZ_CANCEL_PRODORDCF — 取消报工
    # ==================================================================

    def cancel_production_confirmation(
        self,
        confirmation_nr: str,
    ) -> Dict:
        """
        取消报工 (RFC: ZIF_JJGZ_CANCEL_PRODORDCF)。

        Args:
            confirmation_nr: 报工单号

        Returns:
            dict: SAP 返回结果
        """
        return self._call_rfc('ZIF_JJGZ_CANCEL_PRODORDCF', CONFIRMATION_NR=confirmation_nr)
