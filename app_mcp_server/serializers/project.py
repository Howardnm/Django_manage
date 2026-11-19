import logging

from django.utils import timezone
from rest_framework import serializers

from app_project.models import Project, ProjectNode

from .base import (
    AttachmentBriefSerializer,
    FloatDecimalField,
    NADateField,
    NADateTimeMinuteField,
    WarningMixin,
    as_plain,
    attachments_for,
    blank_to_none,
    format_date,
)
from .types import ProjectDetailOut, ProjectListOut

logger = logging.getLogger(__name__)


def _person_label(user):
    """与项目导出同一口径：有姓名用姓名，否则用用户名。"""
    if user is None:
        return None
    full = (user.get_full_name() or "").strip()
    return full or user.username


def _money(value):
    return None if value is None else float(value)


def _minute(value):
    """与进度页「更新于」相同：本地时间，精确到分钟。"""
    if not value:
        return None
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%Y-%m-%d %H:%M")


class ProjectListSerializer(serializers.ModelSerializer):
    manager = serializers.SerializerMethodField()
    current_stage = serializers.CharField(source="get_current_stage_display", read_only=True)
    created_at = NADateField()

    class Meta:
        model = Project
        fields = (
            "id", "code", "name", "manager", "current_stage",
            "progress_percent", "is_terminated", "created_at",
        )

    def get_manager(self, obj):
        return _person_label(obj.manager)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["code"] = blank_to_none(data.get("code"))
        return data


class ProjectNodeSerializer(serializers.ModelSerializer):
    stage = serializers.CharField(source="get_stage_display", read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)
    updated_at = NADateTimeMinuteField()
    failure_reason = serializers.SerializerMethodField()
    feedback_type = serializers.SerializerMethodField()
    workflow = serializers.SerializerMethodField()

    class Meta:
        model = ProjectNode
        fields = (
            "stage", "round", "order", "status", "remark", "updated_at",
            "failure_reason", "feedback_type", "workflow",
        )

    def get_failure_reason(self, obj):
        return obj.failure_reason.name if obj.failure_reason_id else None

    def get_feedback_type(self, obj):
        return obj.feedback_type.name if obj.feedback_type_id else None

    def get_workflow(self, obj):
        instance = obj.workflow_instance
        if instance is None:
            return None
        return {
            "name": instance.definition.name,
            "status": instance.get_status_display(),
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # remark 列是 null=True；空备注统一成 null，别让 agent 去区分 "" 和 null。
        # 字段本身保留：每个阶段节点都要能读到自己的备注和更新时间。
        data["remark"] = blank_to_none(data.get("remark"))
        data["updated_at"] = _minute(instance.updated_at)
        return data


class ProjectDetailSerializer(WarningMixin, ProjectListSerializer):
    description = serializers.CharField(read_only=True)
    grade = serializers.SerializerMethodField()
    business_segment = serializers.SerializerMethodField()
    latest_remark = serializers.CharField(read_only=True)
    quality_score = FloatDecimalField()
    sales_quality_score = FloatDecimalField()
    members = serializers.SerializerMethodField()
    sales_members = serializers.SerializerMethodField()
    business_info = serializers.SerializerMethodField()
    timeline = ProjectNodeSerializer(source="nodes", many=True, read_only=True)
    associated_files = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = ProjectListSerializer.Meta.fields + (
            "description", "grade", "business_segment", "latest_remark",
            "quality_score", "sales_quality_score",
            "members", "sales_members",
            "business_info", "timeline", "associated_files",
        )

    def get_grade(self, obj):
        return obj.grade.name if obj.grade_id else None

    def get_business_segment(self, obj):
        return obj.business_segment.name if obj.business_segment_id else None

    def get_members(self, obj):
        return [
            {
                "name": _person_label(member.user),
                "role": member.get_role_display(),
                "workload_share": _money(member.workload_share),
            }
            for member in sorted(obj.members.all(), key=lambda item: item.pk)
        ]

    def get_sales_members(self, obj):
        return [
            {
                "name": _person_label(member.user),
                "workload_share": _money(member.workload_share),
            }
            for member in sorted(obj.sales_members.all(), key=lambda item: item.pk)
        ]

    def get_business_info(self, obj):
        """无业务档案（ProjectRepository）时返回 None，字段保留而不是被删掉。"""
        repo = getattr(obj, "repository", None)
        if not repo:
            return None
        customer = repo.customer
        material = obj.material
        return {
            "customer": blank_to_none(customer.short_name) if customer else None,
            "customer_code": blank_to_none(customer.customer_code) if customer else None,
            "customer_company_name": blank_to_none(customer.company_name) if customer else None,
            "oem": repo.oem.name if repo.oem_id else None,
            "salesperson": _person_label(repo.salesperson),
            "product_name": blank_to_none(repo.product_name),
            "product_code": blank_to_none(repo.product_code),
            "part_usage": blank_to_none(repo.part_usage),
            "part_color": blank_to_none(repo.part_color),
            "rd_high_feasibility": repo.rd_high_feasibility,
            "biz_high_feasibility": repo.biz_high_feasibility,
            "target_material": material.grade_name if material else None,
            "sap_material_code": blank_to_none(material.sap_material_code) if material else None,
            "material_category": material.category.name if material and material.category_id else None,
            # 不设目标成本 → None（而不是 0，0 是"目标成本为零"这个真实语义）
            "target_cost": _money(repo.target_cost),
            "competitor_price": _money(repo.competitor_price),
            "estimated_order_volume": _money(repo.estimated_order_volume),
            "first_sample_date": format_date(repo.first_sample_date),
            "first_trial_date": format_date(repo.first_trial_date),
            "first_trial_cycle_days": repo.first_trial_cycle_days,
            "pilot_date": format_date(repo.pilot_date),
            "mass_production_date": format_date(repo.mass_production_date),
            "updated_at": _minute(repo.updated_at),
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
        data["description"] = blank_to_none(data.get("description"))
        data["latest_remark"] = blank_to_none(data.get("latest_remark"))
        return self.attach_warnings(data)


def serialize_project(project) -> ProjectListOut:
    """Basic project serialization for list view."""
    return as_plain(ProjectListSerializer(project).data)


def serialize_project_full(project) -> ProjectDetailOut:
    """Ultimate Project Serializer including Archive, Timeline and Files."""
    return as_plain(ProjectDetailSerializer(project).data)
