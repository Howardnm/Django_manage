"""成品 BOM 接口的错误体，形状与 SAP BOM 接口相同。

``FinishedBomPublishError`` 先收成校验错误，其余交给 SAP 那套处理
（未登录、404、SAP 业务拒绝、通信失败）。
"""

from rest_framework.exceptions import ValidationError

from app_material.services.finished_bom_publish import FinishedBomPublishError
from app_sap_services.api.exceptions import sap_bom_exception_handler


def finished_bom_exception_handler(exc, context):
    if isinstance(exc, FinishedBomPublishError):
        exc = ValidationError(exc.detail)
    return sap_bom_exception_handler(exc, context)
