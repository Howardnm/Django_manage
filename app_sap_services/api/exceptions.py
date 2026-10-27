"""
BOM API 的错误体。只挂在 SapBomAPIView 上，不改全局 EXCEPTION_HANDLER。

成功响应不是这个形状。出错时一律::

    {"detail": "简短说明", "code": "...", "messages": [
        {"type": "E", "text": "...", "row": null, "field": null}
    ]}

code 与 HTTP 状态:

    validation_error   400  入参校验失败
    sap_business       400  SAP 业务拒绝（含维护表 T_MSG 里的 E/A）
    not_found          404  展开时没有这张 BOM
    not_authenticated  403  未登录
    sap_transport      502  连不上 SAP，或 RFC 本身失败
"""

from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.response import Response

from app_sap_services.exceptions import (
    SAPBusinessError,
    SAPConfigError,
    SAPConnectionError,
    SAPRfcError,
)
from app_sap_services.schemas.messages import FATAL_TYPES
from app_sap_services.services.bom import BomMaintainError


def sap_bom_exception_handler(exc, context):
    """把本接口抛出的异常收成上面的错误体。

    由 ``SapBomAPIView.get_exception_handler`` 返回，DRF 在
    ``handle_exception`` 里调用。``context`` 是 DRF 传入的视图上下文，这里用不到。

    没认出来的异常返回 None，让 DRF 按原异常抛出去，不要包成 200 或空消息。
    传输失败的正文固定是「SAP 通信失败」：``SAPRfcError`` 的字符串里带调用参数，
    不能写进响应。

    使用示例::

        # 维护被 SAP 拒绝
        {"detail": "组件不存在", "code": "sap_business", "messages": [
            {"type": "E", "text": "组件不存在", "row": 1, "field": "IDNRK"}
        ]}

        # 入参不对
        {"detail": "datuv: 该字段是必填项。", "code": "validation_error",
         "messages": [{"type": "E", "text": "datuv: 该字段是必填项。",
                       "row": null, "field": "datuv"}]}
    """
    if isinstance(exc, ValidationError):
        messages = _flatten_validation(exc.detail)
        detail = messages[0]["text"] if messages else "参数错误"
        return _response(detail, "validation_error", messages, 400)

    if isinstance(exc, NotAuthenticated):
        return _response("未登录", "not_authenticated", [], 403)

    if isinstance(exc, NotFound):
        return _response(_detail_text(exc.detail) or "BOM 不存在", "not_found", [], 404)

    if isinstance(exc, BomMaintainError):
        fatal = next((m for m in exc.messages if m.get("type") in FATAL_TYPES), None)
        detail = (fatal or {}).get("text") or "SAP 拒绝了这次维护"
        return _response(detail, "sap_business", exc.messages, 400)

    if isinstance(exc, SAPBusinessError):
        messages = [
            {"type": m.type, "text": m.text, "row": None, "field": None}
            for m in exc.messages
        ]
        return _response(exc.rtmsg or "SAP 拒绝了这次调用", "sap_business", messages, 400)

    if isinstance(exc, (SAPRfcError, SAPConnectionError, SAPConfigError)):
        # str(SAPRfcError) 带 params，不能放进响应。
        return _response("SAP 通信失败", "sap_transport", [], 502)

    return None


def _response(detail, code, messages, status):
    """组装统一错误体。``messages`` 没有时传空列表，不要省掉这个键。"""
    return Response(
        {"detail": detail, "code": code, "messages": messages},
        status=status,
    )


def _detail_text(detail) -> str:
    """取出 DRF 的单条 detail。列表或字典留给 ``_flatten_validation``，这里不当成一句说明。"""
    if detail is None:
        return ""
    if isinstance(detail, (list, dict)):
        return ""
    return str(detail)


def _flatten_validation(detail, field=""):
    """把 DRF 的嵌套校验错误摊成一条条 message。

    ``lines`` 是 many=True，通过的那一行是空 dict，跳过。
    出错的行带上下标，字段名变成 ``lines.0.posnr`` 这种路径。

    Args:
        detail: ValidationError.detail，可能是字符串、列表或字典。
        field: 当前这一层的字段路径，递归时往下接。

    Returns:
        list[dict]，每项都是 ``{"type", "text", "row", "field"}``。
    """
    if isinstance(detail, dict):
        messages = []
        for key, value in detail.items():
            nested = key if not field else f"{field}.{key}"
            messages.extend(_flatten_validation(value, nested))
        return messages

    if isinstance(detail, list):
        messages = []
        for index, item in enumerate(detail):
            if isinstance(item, (dict, list)):
                nested = f"{field}.{index}" if field else str(index)
                messages.extend(_flatten_validation(item, nested))
            elif item not in ({}, []):
                messages.append(_validation_message(field, item))
        return messages

    return [_validation_message(field, detail)]


def _validation_message(field, detail) -> dict:
    """一条校验错误。有字段时正文写成 ``字段: 原因``，``type`` 固定为 E。"""
    text = str(detail)
    if field:
        text = f"{field}: {text}"
    return {
        "type": "E",
        "text": text,
        "row": None,
        "field": field or None,
    }
