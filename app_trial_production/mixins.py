from app_user.mixins import UnifiedAccessMixin


class TrialProductionAccessMixin(UnifiedAccessMixin):
    """试验排产模块 — 基础权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    操作员数据视野放宽逻辑已移除——角色通过 ModuleAccessConfig 分配后自然有权访问。
    """

    module_code = 'trial_production'
    user_link_fields = ['creator', 'extruder_operator', 'operator',
                        'assigned_to', 'recorded_by']


class ExtrusionTaskAccessMixin(TrialProductionAccessMixin):
    """挤出任务 — 仅挤出操作员。"""

    module_code = 'trial_production.extrusion_task'


class DashboardAccessMixin(TrialProductionAccessMixin):
    """排产总览 — 仅研发工程师。"""

    module_code = 'trial_production.dashboard'


class RndAccessMixin(TrialProductionAccessMixin):
    """排产发起/审批 — 仅研发工程师，按项目负责人隔离。"""

    module_code = 'trial_production.rnd'
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
    """样品库存 — 研发工程师 + 操作员可访问。"""

    module_code = 'trial_production.sample_inventory'
