from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin


class ProjectAccessMixin(UnifiedAccessMixin):
    """项目模块权限管控。

    支持协同成员穿透查看。L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'project'
    module_name = '项目管理中心'
    user_link_fields = ['manager']

    def get_queryset(self):
        """L4/L5 隔离结果 ∪ 协同成员/销售成员穿透。"""
        user = self.request.user
        qs = super().get_queryset()

        if qs is None:
            return None

        if hasattr(qs.model, 'members'):
            member_q = Q(members__user=user)
            # 销售成员同样可穿透查看（了解自己的销售项目）
            if hasattr(qs.model, 'sales_members'):
                member_q |= Q(sales_members__user=user)
            # `super().get_queryset()` 的 distinct 状态不确定：
            #   - 超管路径直接返回 qs（非 distinct）
            #   - L5 隔离开启时返回 .distinct()
            # Django 的 `|` 合并要求两侧 distinct 状态一致，故两侧都显式 .distinct()，
            # 再整体去重（对已 distinct 的查询，.distinct() 幂等）。
            return (qs.distinct() | qs.model.objects.filter(member_q).distinct()).distinct()

        return qs

    def check_object_permission(self, obj):
        """对象级检查：(负责人/同部门) OR 协同成员/销售成员。"""
        user = self.request.user
        if user.is_superuser:
            return True

        try:
            return super().check_object_permission(obj)
        except PermissionDenied:
            # 协同成员穿透查看
            if hasattr(obj, 'members') and obj.members.filter(user=user).exists():
                return True
            # 销售成员穿透查看（了解自己的销售项目）
            if hasattr(obj, 'sales_members') and obj.sales_members.filter(user=user).exists():
                return True
            raise


class PerformanceManagementMixin(ProjectAccessMixin):
    """绩效管理写操作权限 — 高职级人员操作评分规则。"""

    module_code = 'project.performance_management'
    module_name = '绩效管理'


class PerformanceRuleReadMixin(ProjectAccessMixin):
    """绩效规则查看权限 — 研发工程师 + 业务经理查看。"""

    module_code = 'project.performance_read'
    module_name = '绩效规则查看'


class SharedConfigMixin(ProjectAccessMixin):
    """全局配置表权限 — 组织级共享资源。"""

    module_code = 'project.shared_config'
    module_name = '全局配置表'
