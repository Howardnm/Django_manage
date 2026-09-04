from rest_framework import serializers

from app_project.models import Project, ProjectNode

from .base import (
    AttachmentBriefSerializer,
    NADateField,
    NADateTimeMinuteField,
    as_plain,
    attachments_for,
)


class ProjectListSerializer(serializers.ModelSerializer):
    manager = serializers.CharField(source="manager.username", default="N/A", read_only=True)
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
    remark = serializers.CharField(default="", allow_null=True, read_only=True)
    updated_at = NADateTimeMinuteField()

    class Meta:
        model = ProjectNode
        fields = ("stage", "round", "status", "remark", "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["remark"] = data.get("remark") or ""
        return data


class ProjectDetailSerializer(ProjectListSerializer):
    business_info = serializers.SerializerMethodField()
    timeline = ProjectNodeSerializer(source="nodes", many=True, read_only=True)
    associated_files = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = ProjectListSerializer.Meta.fields + (
            "business_info", "timeline", "associated_files",
        )

    def get_business_info(self, obj):
        repo = getattr(obj, "repository", None)
        if not repo:
            return None
        salesperson = repo.salesperson
        if salesperson:
            salesperson_name = salesperson.get_full_name() or salesperson.username
        else:
            salesperson_name = "N/A"
        return {
            "customer": repo.customer.short_name if repo.customer else "N/A",
            "oem": repo.oem.name if repo.oem else "N/A",
            "salesperson": salesperson_name,
            "product_name": repo.product_name,
            "target_material": obj.material.grade_name if obj.material else "Not Selected",
            "target_cost": float(repo.target_cost or 0),
        }

    def get_associated_files(self, obj):
        repo = getattr(obj, "repository", None)
        if not repo:
            return []
        try:
            return AttachmentBriefSerializer(attachments_for(repo), many=True).data
        except Exception:
            return []

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("business_info") is None:
            data.pop("business_info", None)
        return data


def serialize_project(project):
    """Basic project serialization for list view."""
    return as_plain(ProjectListSerializer(project).data)


def serialize_project_full(project):
    """Ultimate Project Serializer including Archive, Timeline and Files."""
    return as_plain(ProjectDetailSerializer(project).data)
