from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class TrialProductionAccessMixin(UnifiedAccessMixin):
    """试验排产模块 — 基础权限管控"""
    user_link_fields = ['creator', 'extruder_operator', 'operator',
                        'assigned_to', 'recorded_by']
    identity_required = [IdentityConfig.R_ENGINEER, IdentityConfig.R_EXTRUSION_OP]

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return None
        user = self.request.user

        # 生产操作员按任务分配放宽数据可见范围
        if user.user_type in [
            IdentityConfig.R_EXTRUSION_OP,
            IdentityConfig.R_COLOR_OP,
            IdentityConfig.R_INJECTION_OP,
            IdentityConfig.R_TESTING_OP,
        ]:
            model = qs.model
            model_fields = [f.name for f in model._meta.get_fields()]
            operator_field_map = {
                IdentityConfig.R_EXTRUSION_OP: 'operator',
                IdentityConfig.R_COLOR_OP: 'operator',
                IdentityConfig.R_INJECTION_OP: 'operator',
                IdentityConfig.R_TESTING_OP: 'assigned_to',
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
    """挤出任务 — 仅挤出操作员"""
    identity_required = [IdentityConfig.R_EXTRUSION_OP]


class DashboardAccessMixin(TrialProductionAccessMixin):
    """排产总览 — 仅研发工程师"""
    identity_required = [IdentityConfig.R_ENGINEER]
    enforce_dept_isolation = False


class RndAccessMixin(TrialProductionAccessMixin):
    """排产发起/审批 — 仅研发工程师，按项目负责人隔离"""
    identity_required = [IdentityConfig.R_ENGINEER]
    user_link_fields = ['manager']

    @staticmethod
    def check_project_ownership(project, user):
        """验证用户是否属于该项目（负责人或成员），无权时抛出 PermissionDenied"""
        if user.is_superuser:
            return
        if project.manager_id == user.pk:
            return
        if project.members.filter(user=user).exists():
            return
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("您不是该项目的负责人或成员，无权操作此项目")


class SampleInventoryAccessMixin(TrialProductionAccessMixin):
    """样品库存 — 研发工程师 + 挤出操作员可访问，不做部门隔离"""
    identity_required = [IdentityConfig.R_ENGINEER, IdentityConfig.R_EXTRUSION_OP]
    enforce_dept_isolation = False
