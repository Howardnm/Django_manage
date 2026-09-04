"""MCP 只读序列化公共字段。

输出给 AI：日期为 YYYY-MM-DD / N/A，Decimal 为 JSON number。
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


def format_date(dt) -> str:
    """YYYY-MM-DD，空值返回 N/A。"""
    return dt.strftime("%Y-%m-%d") if dt else "N/A"


class NADateField(serializers.DateTimeField):
    """有值 → YYYY-MM-DD，空 → N/A。兼容 DateField / DateTimeField。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return "N/A"
        return value.strftime(self.format)


class NADateTimeMinuteField(serializers.DateTimeField):
    """有值 → YYYY-MM-DD HH:MM，空 → N/A。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d %H:%M")
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return "N/A"
        return value.strftime(self.format)


class FloatDecimalField(serializers.Field):
    """Decimal / None → float（None 与 0 都输出 0.0）。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return float(value or 0)


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
