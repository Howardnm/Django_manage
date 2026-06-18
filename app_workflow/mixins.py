from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class WorkflowAccessMixin(UnifiedAccessMixin):
    """审批流程模块权限管控（L1 内部全员准入 / L4 关闭部门隔离，审批跨部门协作）"""

    identity_required = IdentityConfig.INTERNAL_STAFF
    enforce_dept_isolation = False
