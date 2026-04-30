from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class WorkflowAccessMixin(UnifiedAccessMixin):
    """审批流程模块 4D 权限控制"""

    identity_required = IdentityConfig.INTERNAL_STAFF

    # 审批流程跨部门协作，不启用部门隔离
    enforce_dept_isolation = False
