from django.core.exceptions import PermissionDenied
from app_user.mixins import UnifiedAccessMixin


class FormManagementAccessMixin(UnifiedAccessMixin):
    """表单管理模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'form_management'
    module_name = '表单管理中心'
    user_link_fields = ['submitted_by', 'manager', 'creator', 'user', 'owner', 'uploader', 'salesperson']

    def check_object_permission(self, obj):
        """表单附件查看权限：仅提交者 + 审批流程参与人。"""
        user = self.request.user
        if user.is_superuser:
            return True

        # 提交者本人
        if hasattr(obj, 'submitted_by') and obj.submitted_by_id == user.pk:
            return True

        # 审批流程中的审批人（已分配过任务）
        if hasattr(obj, 'workflow_instance_id') and obj.workflow_instance_id:
            from app_workflow.models import WorkflowTask
            if WorkflowTask.objects.filter(
                instance_id=obj.workflow_instance_id,
                assigned_to=user,
            ).exists():
                return True

        raise PermissionDenied("您无权查看该表单的附件")
