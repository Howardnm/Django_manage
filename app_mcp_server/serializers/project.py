import logging

from rest_framework import serializers

from app_project.models import Project, ProjectNode

from .base import (
    AttachmentBriefSerializer,
    NADateField,
    NADateTimeMinuteField,
    WarningMixin,
    as_plain,
    attachments_for,
    blank_to_none,
)
from .types import ProjectDetailOut, ProjectListOut

logger = logging.getLogger(__name__)


class ProjectListSerializer(serializers.ModelSerializer):
    manager = serializers.CharField(source="manager.username", read_only=True)
    current_stage = serializers.CharField(source="get_current_stage_display", read_only=True)
    created_at = NADateField()

    class Meta:
        model = Project
        fields = (
            "id", "name", "manager", "current_stage",
            "progress_percent", "is_terminated", "created_at",
        )


class ProjectNodeSerializer(serializers.ModelSerializer):
    stage = serializers.CharField(source="get_stage_display", read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)
    updated_at = NADateTimeMinuteField()

    class Meta:
        model = ProjectNode
        fields = ("stage", "round", "status", "remark", "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # remark 列是 null=True；空备注统一成 null，别让 agent 去区分 "" 和 null
        data["remark"] = blank_to_none(data.get("remark"))
        return data


class ProjectDetailSerializer(WarningMixin, ProjectListSerializer):
    business_info = serializers.SerializerMethodField()
    timeline = ProjectNodeSerializer(source="nodes", many=True, read_only=True)
    associated_files = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = ProjectListSerializer.Meta.fields + (
            "business_info", "timeline", "associated_files",
        )

    def get_business_info(self, obj):
        """无业务档案（ProjectRepository）时返回 None，字段保留而不是被删掉。"""
        repo = getattr(obj, "repository", None)
        if not repo:
            return None
        salesperson = repo.salesperson
        if salesperson:
            salesperson_name = salesperson.get_full_name() or salesperson.username
        else:
            salesperson_name = None
        return {
            "customer": repo.customer.short_name if repo.customer else None,
            "oem": repo.oem.name if repo.oem else None,
            "salesperson": salesperson_name,
            "product_name": blank_to_none(repo.product_name),
            "target_material": obj.material.grade_name if obj.material else None,
            # 不设目标成本 → None（而不是 0，0 是"目标成本为零"这个真实语义）
            "target_cost": float(repo.target_cost) if repo.target_cost is not None else None,
        }

    def get_associated_files(self, obj):
        """三种情况必须可区分：无档案 / 没附件 / 读取失败。

        前两者返回 None 或 []，读取失败返回 None 并加 warning——不能像以前那样
        全部塌成 []，让 agent 以为"这个项目没有附件"。
        """
        repo = getattr(obj, "repository", None)
        if not repo:
            return None
        try:
            return AttachmentBriefSerializer(attachments_for(repo), many=True).data
        except Exception as exc:
            logger.warning(
                "MCP attachment serialization failed project=%s: %s", obj.pk, exc,
                exc_info=True,
            )
            self.add_warning(
                f"关联文件读取失败（{type(exc).__name__}），associated_files 为 null "
                "不代表该项目没有文件。",
            )
            return None

    def to_representation(self, instance):
        self.reset_warnings()
        data = super().to_representation(instance)
        return self.attach_warnings(data)


def serialize_project(project) -> ProjectListOut:
    """Basic project serialization for list view."""
    return as_plain(ProjectListSerializer(project).data)


def serialize_project_full(project) -> ProjectDetailOut:
    """Ultimate Project Serializer including Archive, Timeline and Files."""
    return as_plain(ProjectDetailSerializer(project).data)
