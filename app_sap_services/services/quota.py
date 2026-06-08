"""
配额协议 / 供应链 SAP 服务。

已实现 RFC:
- ZRFC_QUOTA_CREATE      — 创建配额协议
- ZRFC_RV_CONDITION_COPY — 创建条件记录
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class QuotaService(BaseSAPService):
    """
    配额协议 / 供应链服务。

    使用示例:
        from app_sap_services import sap_quota

        sap_quota.create_quota(quota_items=[...])
        sap_quota.copy_condition(condition_data={...})
    """

    # ==================================================================
    # ZRFC_QUOTA_CREATE — 创建配额协议
    # ==================================================================

    def create_quota(
        self,
        items: List[Dict],
    ) -> Dict:
        """
        创建配额协议 (RFC: ZRFC_QUOTA_CREATE)。

        Args:
            items: 配额协议行项目列表，每条记录包含:
                WERKS  — 工厂
                MATNR  — 物料编号
                LIFNR  — 供应商编号
                QUOTE  — 配额比例
                VDATU  — 有效期从 (YYYYMMDD)
                BDATU  — 有效期至 (YYYYMMDD)
                BESKZ  — 采购类型
                SOBES  — 特殊采购类型
                MMSEG  — 物料组
                LINID  — 行号
                MTYPE  — 物料类型

        Returns:
            dict: SAP 返回结果
        """
        return self._call_rfc('ZRFC_QUOTA_CREATE', IT_ITEM=items)

    # ==================================================================
    # ZRFC_RV_CONDITION_COPY — 创建条件记录
    # ==================================================================

    def copy_condition(
        self,
        condition_data: Dict,
    ) -> Dict:
        """
        创建条件记录 (RFC: ZRFC_RV_CONDITION_COPY)。

        Args:
            condition_data: 条件记录数据，具体字段请参考 SAP 接口文档

        Returns:
            dict: SAP 返回结果
        """
        return self._call_rfc('ZRFC_RV_CONDITION_COPY', **condition_data)
