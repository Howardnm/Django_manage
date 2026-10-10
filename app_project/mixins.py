from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin


class ProjectAccessMixin(UnifiedAccessMixin):
    """项目模块权限管控。

    支持协同成员、销售成员，以及组/部门/子公司组织负责人穿透查看。
    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    组织负责人只放行查看，编辑仍走 check_edit_permission。
    """

    module_code = 'project'
    module_name = '项目管理中心'
    module_description = '项目管理中心。按负责人隔离，叠加协同成员/销售成员及组/部门/子公司负责人穿透查看。'
    user_link_fields = ['manager']

    def _org_leader_project_q(self, user):
        """组织角色指派对应的项目可见范围。

        只认 OrgRoleAssignment 的 role.scope，不看 User.subsidiary，也不跨级升级：
        组长只看负责人属于该工作组的项目，部门负责人只看本部门，子公司负责人只看本公司。
        含副职（不筛 is_primary）。空指派是空子查询，匹配不到行。
        """
        from app_user.models import OrgRoleAssignment

        assigned = OrgRoleAssignment.objects.filter(user=user)
        return (
            Q(manager__work_groups__in=assigned.filter(
                role__scope='workgroup',
                workgroup__is_active=True,
            ).values('workgroup_id'))
            | Q(manager__department_id__in=assigned.filter(
                role__scope='department',
                department__isnull=False,
            ).values('department_id'))
            | Q(manager__subsidiary_id__in=assigned.filter(
                role__scope='subsidiary',
                subsidiary__isnull=False,
            ).values('subsidiary_id'))
        )

    def _leads_project_org(self, user, project):
        """对象级：一条查询判断用户是否因组织指派只读可见该项目。"""
        from app_user.models import OrgRoleAssignment

        manager = getattr(project, 'manager', None)
        if manager is None:
            return False
        scope_q = Q(
            role__scope='workgroup',
            workgroup__is_active=True,
            workgroup__members=manager,
        )
        if manager.department_id:
            scope_q |= Q(role__scope='department', department_id=manager.department_id)
        if manager.subsidiary_id:
            scope_q |= Q(role__scope='subsidiary', subsidiary_id=manager.subsidiary_id)
        return OrgRoleAssignment.objects.filter(user=user).filter(scope_q).exists()

    def get_queryset(self):
        """L4/L5 隔离结果 ∪ 协同成员/销售成员 ∪ 组织负责人穿透。"""
        from app_project.models import Project

        user = self.request.user
        qs = super().get_queryset()

        if qs is None:
            return None

        if hasattr(qs.model, 'members'):
            member_q = Q(members__user=user)
            # 销售成员同样可穿透查看（了解自己的销售项目）
            if hasattr(qs.model, 'sales_members'):
                member_q |= Q(sales_members__user=user)
            # 组织负责人穿透只加在 Project 上，避免绩效规则/全局配置表被误放行
            if qs.model is Project:
                member_q |= self._org_leader_project_q(user)
            # `super().get_queryset()` 的 distinct 状态不确定：
            #   - 超管路径直接返回 qs（非 distinct）
            #   - L5 隔离开启时返回 .distinct()
            # Django 的 `|` 合并要求两侧 distinct 状态一致，故两侧都显式 .distinct()，
            # 再整体去重（对已 distinct 的查询，.distinct() 幂等）。
            return (qs.distinct() | qs.model.objects.filter(member_q).distinct()).distinct()

        return qs

    def check_object_permission(self, obj):
        """对象级检查：(负责人/同部门/同组) OR 协同成员/销售成员 OR 组织负责人。"""
        from app_project.models import Project

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
            if isinstance(obj, Project) and self._leads_project_org(user, obj):
                return True
            raise


class PerformanceManagementMixin(ProjectAccessMixin):
    """绩效管理写操作权限 — 高职级人员操作评分规则。"""

    module_code = 'project.performance_management'
    module_name = '绩效管理'
    module_description = '绩效管理写操作。高职级人员操作评分规则。'


class PerformanceRuleReadMixin(ProjectAccessMixin):
    """绩效规则查看权限 — 研发工程师 + 业务经理查看。"""

    module_code = 'project.performance_read'
    module_name = '绩效规则查看'
    module_description = '绩效规则查看。研发工程师 + 业务经理查看。'


class SharedConfigMixin(ProjectAccessMixin):
    """全局配置表权限 — 组织级共享资源。"""

    module_code = 'project.shared_config'
    module_name = '全局配置表'
    module_description = '全局配置表。组织级共享资源。'
