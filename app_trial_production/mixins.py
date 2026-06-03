from app_user.mixins import UnifiedAccessMixin, IdentityConfig
from app_user.models import User


class TrialProductionAccessMixin(UnifiedAccessMixin):
    """试验排产模块 — 基础权限管控"""
    user_link_fields = ['creator', 'extruder_operator', 'assigned_operator',
                        'assigned_to', 'recorded_by', 'filled_by']
    identity_required = IdentityConfig.INTERNAL_STAFF
    enforce_dept_isolation = True
    permission_required = []

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return None
        user = self.request.user
        if user.is_superuser:
            return qs

        # 生产操作员按任务分配字段放宽数据可见范围
        if user.user_type in [
            User.UserType.EXTRUSION_OPERATOR,
            User.UserType.COLOR_OPERATOR,
            User.UserType.INJECTION_OPERATOR,
            User.UserType.TESTING_OPERATOR,
        ]:
            model = qs.model
            model_fields = [f.name for f in model._meta.get_fields()]
            operator_field_map = {
                User.UserType.EXTRUSION_OPERATOR: 'extruder_operator',
                User.UserType.COLOR_OPERATOR: None,  # 配色基于 needs_color_matching，由视图层 filter
                User.UserType.INJECTION_OPERATOR: 'assigned_operator',
                User.UserType.TESTING_OPERATOR: 'assigned_to',
            }
            field = operator_field_map.get(user.user_type)
            if field and field in model_fields:
                from django.db.models import Q
                qs = qs.filter(
                    Q(**{f"{field}": user}) |
                    Q(**{f"{field}__isnull": True})
                )
        return qs


class ExtrusionTaskAccessMixin(TrialProductionAccessMixin):
    """挤出任务 — 仅挤出操作员 + 技术核心 + 管理员"""
    identity_required = IdentityConfig.TECH_CORE + [
        User.UserType.EXTRUSION_OPERATOR,
    ]


class ColorTaskAccessMixin(TrialProductionAccessMixin):
    """配色任务 — 仅配色员 + 技术核心 + 管理员"""
    identity_required = IdentityConfig.TECH_CORE + [
        User.UserType.COLOR_OPERATOR,
    ]


class InjectionTaskAccessMixin(TrialProductionAccessMixin):
    """注塑任务 — 仅注塑操作员 + 技术核心 + 管理员"""
    identity_required = IdentityConfig.TECH_CORE + [
        User.UserType.INJECTION_OPERATOR,
    ]


class TestingTaskAccessMixin(TrialProductionAccessMixin):
    """测试任务 — 仅测试员 + 技术核心 + 管理员"""
    identity_required = IdentityConfig.TECH_CORE + [
        User.UserType.TESTING_OPERATOR,
    ]


class DashboardAccessMixin(TrialProductionAccessMixin):
    """排产总览 — 仅研发人员 + 管理员"""
    identity_required = IdentityConfig.RND_ONLY
    enforce_dept_isolation = False


class RndAccessMixin(TrialProductionAccessMixin):
    """排产发起/审批 — 仅研发人员 + 管理员，按项目负责人隔离"""
    identity_required = IdentityConfig.RND_ONLY
    user_link_fields = ['manager']

    @staticmethod
    def check_project_ownership(project, user):
        """验证用户是否属于该项目（负责人或成员）"""
        if user.is_superuser:
            return True
        if project.manager_id == user.pk:
            return True
        return project.members.filter(user=user).exists()
