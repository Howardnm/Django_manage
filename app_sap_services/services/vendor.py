"""
供应商校验 SAP 服务。

已实现 RFC:
- ZFG_CHECK_VENDOR — 校验供应商
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService


class VendorService(BaseSAPService):
    """
    供应商服务。

    使用示例:
        from app_sap_services import sap_vendor

        result = sap_vendor.check_vendor('0000100001')
    """

    # ==================================================================
    # ZFG_CHECK_VENDOR — 校验供应商
    # ==================================================================

    def check_vendor(
        self,
        vendor_code: str,
        company_code: Optional[str] = None,
    ) -> Dict:
        """
        校验供应商编码是否在 SAP 中存在 (RFC: ZFG_CHECK_VENDOR)。

        Args:
            vendor_code:  供应商编码 (LIFNR)
            company_code: 公司代码 (BUKRS)，可选

        Returns:
            dict: SAP 返回结果（具体字段待实际调用后确认）
        """
        params = {'LIFNR': vendor_code}
        if company_code:
            params['BUKRS'] = company_code

        return self._call_rfc('ZFG_CHECK_VENDOR', **params)
