"""MCP 只读序列化公共字段。

输出给 AI：**空属性一律输出 null**，不用 "N/A" 之类的字符串哨兵——
agent 必须能区分"这个字段没有值"和"这个字段的值就是 N/A 这个字符串"。
日期为 YYYY-MM-DD，Decimal 为 JSON number。
不改全局 REST_FRAMEWORK（目录 API 仍用 ISO / Decimal 字符串）。
"""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList

from app_attachment.models import Attachment


def as_plain(data):
    """DRF ReturnDict/ReturnList → 普通 dict/list，便于 MCP structured output。"""
    if isinstance(data, (ReturnDict, dict)):
        return {k: as_plain(v) for k, v in data.items()}
    if isinstance(data, (ReturnList, list, tuple)):
        return [as_plain(v) for v in data]
    if isinstance(data, Decimal):
        return float(data)
    return data


def json_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def blank_to_none(value):
    """空字符串 → None。空串和 null 对 agent 是同一件事，别让它猜。"""
    return value if value not in ("", None) else None


def format_date(dt) -> str | None:
    """YYYY-MM-DD，空值返回 None。"""
    return dt.strftime("%Y-%m-%d") if dt else None


class NADateField(serializers.DateTimeField):
    """有值 → YYYY-MM-DD，空 → null。兼容 DateField / DateTimeField。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return None
        return value.strftime(self.format)


class NADateTimeMinuteField(serializers.DateTimeField):
    """有值 → YYYY-MM-DD HH:MM，空 → null。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d %H:%M")
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return None
        return value.strftime(self.format)


class FloatDecimalField(serializers.Field):
    """Decimal → float，None 保持 None（"没有值" ≠ 0）。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return None if value is None else float(value)


class WarningMixin:
    """让 SerializerMethodField 能声明"这块数据我不确定"，输出到 warnings 字段。

    DRF 的 many=True 复用同一个 child 实例逐项渲染，所以必须在每次
    to_representation 开头重置，否则前一条的 warning 会串到后一条。
    """

    def reset_warnings(self):
        self._mcp_warnings = []

    def add_warning(self, message):
        if not hasattr(self, "_mcp_warnings"):
            self._mcp_warnings = []
        if message not in self._mcp_warnings:
            self._mcp_warnings.append(message)

    def attach_warnings(self, data):
        warnings = getattr(self, "_mcp_warnings", None)
        if warnings:
            data["warnings"] = list(warnings)
        return data


def attachments_for(obj):
    """父对象上未删除的附件，按上传时间倒序。"""
    ct = ContentType.objects.get_for_model(obj)
    return Attachment.objects.filter(
        content_type=ct, object_id=obj.pk, is_deleted=False,
    ).order_by("-uploaded_at")


class AttachmentBriefSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name", read_only=True)
    type = serializers.CharField(source="category", read_only=True)
    uploaded_at = NADateField()

    class Meta:
        model = Attachment
        fields = ("name", "type", "version", "uploaded_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # display_name / category 都是 blank=True 的列，空串对 agent 无意义
        data["name"] = blank_to_none(data.get("name"))
        data["type"] = blank_to_none(data.get("type"))
        return data
