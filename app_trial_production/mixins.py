from app_user.mixins import UnifiedAccessMixin


class TrialProductionAccessMixin(UnifiedAccessMixin):
    """试验排产模块 — 基础权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    操作员数据视野放宽逻辑已移除——角色通过 ModuleAccessConfig 分配后自然有权访问。
    """

    module_code = 'trial_production'
    module_name = '试验排产中心'
    module_description = '试验排产中心基础（子模块继承的默认隔离，creator/操作员等所有者维度）。'
    user_link_fields = ['creator', 'extruder_operator', 'operator',
                        'assigned_to', 'recorded_by']


class ExtrusionTaskAccessMixin(TrialProductionAccessMixin):
    """挤出任务 — 仅挤出操作员。"""

    module_code = 'trial_production.extrusion_task'
    module_name = '挤出任务'
    module_description = '挤出任务。仅挤出工程师；按工单所有者隔离。'


class DashboardAccessMixin(TrialProductionAccessMixin):
    """排产总览 — 仅研发工程师。"""

    module_code = 'trial_production.dashboard'
    module_name = '排产总览'
    module_description = '排产总览。仅研发工程师。'


class OrderManageAccessMixin(TrialProductionAccessMixin):
    """工单管理 — 详情/打印等敏感操作。

    研发工程师（order_manage 角色组）按 L4/L5 隔离查看；
    挤出工程师（extrusion_task 角色组）可查看所有工单详情，跳过 L4/L5 隔离。
    删除工单由 RndAccessMixin 单独控制。
    """

    module_code = 'trial_production.order_manage'
    module_name = '工单管理'
    module_description = '工单管理详情/打印。研发按 L4/L5 隔离；挤出工程师（extrusion_task 角色组）跳过隔离看全部。'

    def has_permission(self):
        """准入：order_manage 角色组放行；挤出工程师通过 extrusion_task 角色组放行。"""
        if super().has_permission():
            return True
        # 挤出工程师：extrusion_task 角色组 → 可查看工单详情/打印
        return ExtrusionTaskAccessMixin.user_has_access(self.request.user)

    def check_object_permission(self, obj):
        """数据隔离：挤出工程师跳过 L4/L5（可看所有工单）；研发工程师仍走隔离。"""
        if ExtrusionTaskAccessMixin.user_has_access(self.request.user):
            return True  # 挤出工程师放行所有工单
        return super().check_object_permission(obj)


class RndAccessMixin(TrialProductionAccessMixin):
    """排产发起/审批 — 仅研发工程师，按项目负责人隔离。"""

    module_code = 'trial_production.rnd'
    module_name = '排产发起/审批'
    module_description = '排产发起/审批。仅研发工程师，按项目负责人/成员隔离。'
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
    module_name = '样品库存'
    module_description = '样品库存。研发工程师 + 操作员可访问。'
