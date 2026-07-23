from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin


class ProjectAccessMixin(UnifiedAccessMixin):
    """项目模块权限管控。

    支持协同成员穿透查看。L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'project'
    user_link_fields = ['manager']

    def get_queryset(self):
        """L4/L5 隔离结果 ∪ 协同成员穿透。"""
        user = self.request.user
        qs = super().get_queryset()

        if qs is None:
            return None

        if hasattr(qs.model, 'members'):
            member_q = Q(members__user=user)
            return (qs | qs.model.objects.filter(member_q)).distinct()

        return qs

    def check_object_permission(self, obj):
        """对象级检查：(负责人/同部门) OR 协同成员。"""
        user = self.request.user
        if user.is_superuser:
            return True

        try:
            return super().check_object_permission(obj)
        except PermissionDenied:
            if hasattr(obj, 'members'):
                if obj.members.filter(user=user).exists():
                    return True
            raise


class PerformanceManagementMixin(ProjectAccessMixin):
    """绩效管理写操作权限 — 高职级人员操作评分规则。"""

    module_code = 'project.performance_management'


class PerformanceRuleReadMixin(ProjectAccessMixin):
    """绩效规则查看权限 — 研发工程师 + 业务经理查看。"""

    module_code = 'project.performance_read'


class SharedConfigMixin(ProjectAccessMixin):
    """全局配置表权限 — 组织级共享资源。"""

    module_code = 'project.shared_config'
