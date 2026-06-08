"""
客户主数据 SAP 服务。

已实现 RFC:
- ZRFC_GET_CUSTOMER       — 读取客户主数据
- ZRFC_MODIFY_CUSTOMER    — 维护客户主数据
- ZRFC_GET_KNMT           — 读取客户物料信息
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class CustomerService(BaseSAPService):
    """
    客户主数据服务。

    使用示例:
        from app_sap_services import sap_customer

        # 按客户编号查询
        customers = sap_customer.get_customer(partner='0000100001')

        # 查询客户物料信息
        records = sap_customer.get_customer_material(
            customer_nr='0000100001',
            material_nr='A01001*',
        )
    """

    # ==================================================================
    # ZRFC_GET_CUSTOMER — 读取客户主数据
    # ==================================================================

    def get_customer(
        self,
        partner: Optional[str] = None,
        sales_org: Optional[str] = None,
        company_code: Optional[str] = None,
        dist_channel: Optional[str] = None,
    ) -> Dict[str, List[Dict]]:
        """
        读取客户主数据 (RFC: ZRFC_GET_CUSTOMER)。

        Args:
            partner: 客户编号 (KUNNR)，支持通配符 *
                     - '0000100001' = 精确查询
                     - '00001*'     = 模糊查询
            sales_org: 销售组织 (VKORG)
                       - '1010' = 广东顺采
                       - '2010' = 佛山顺采
            company_code: 公司代码 (BUKRS)
            dist_channel: 分销渠道 (VTWEG)
                          - '10' = 零售
                          - '20' = 批发

        Returns:
            dict 包含以下表:
                TB_KNA1  — 客户基本信息 (KUNNR, NAME1, ORT01, PSTLZ, REGIO...)
                TB_KNB1  — 公司代码数据
                TB_KNVV  — 销售视图
                TB_UKMBP — 信用管理数据
        """
        table_params = {}

        if partner is not None:
            option = 'CP' if '*' in str(partner) else 'EQ'
            table_params['S_PARTNER'] = [self.build_range('I', option, str(partner))]

        if sales_org is not None:
            table_params['S_VKORG'] = [self.build_range('I', 'EQ', str(sales_org))]

        if company_code is not None:
            table_params['S_BUKRS'] = [self.build_range('I', 'EQ', str(company_code))]

        if dist_channel is not None:
            table_params['S_VTWEG'] = [self.build_range('I', 'EQ', str(dist_channel))]

        return self._call_rfc('ZRFC_GET_CUSTOMER', **table_params)

    # ==================================================================
    # ZRFC_MODIFY_CUSTOMER — 维护客户主数据
    # ==================================================================

    def modify_customer(
        self,
        customer_data: Dict,
    ) -> Dict:
        """
        维护客户主数据 (RFC: ZRFC_MODIFY_CUSTOMER)。

        Args:
            customer_data: 客户数据字典，具体字段请参考 SAP 接口文档

        Returns:
            dict: SAP 返回结果（含成功/失败状态）
        """
        return self._call_rfc('ZRFC_MODIFY_CUSTOMER', **customer_data)

    # ==================================================================
    # ZRFC_GET_KNMT — 读取客户物料信息
    # ==================================================================

    def get_customer_material(
        self,
        customer_nr: Optional[str] = None,
        material_nr: Optional[str] = None,
        sales_org: Optional[str] = None,
    ) -> List[Dict]:
        """
        读取客户物料信息 (RFC: ZRFC_GET_KNMT)。

        Args:
            customer_nr: 客户编号 (KUNNR)
                         - 精确: '0000100001'
                         - 模糊: '00001*'
            material_nr: 物料编号 (MATNR)
                         - 精确: 'A01001000003'
                         - 模糊: 'A01*'
            sales_org: 销售组织 (VKORG)

        Returns:
            list[dict]: 客户物料对应关系列表
        """
        table_params = {}

        if customer_nr is not None:
            option = 'CP' if '*' in str(customer_nr) else 'EQ'
            table_params['S_KUNNR'] = [self.build_range('I', option, str(customer_nr))]

        if material_nr is not None:
            option = 'CP' if '*' in str(material_nr) else 'EQ'
            table_params['S_MATNR'] = [self.build_range('I', option, str(material_nr))]

        if sales_org is not None:
            table_params['S_VKORG'] = [self.build_range('I', 'EQ', str(sales_org))]

        result = self._call_rfc('ZRFC_GET_KNMT', **table_params)
        return self.parse_result(result, 'IT_OUTPUT')
