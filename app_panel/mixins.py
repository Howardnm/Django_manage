from app_user.mixins import UnifiedAccessMixin


class PanelAccessMixin(UnifiedAccessMixin):
    """工作台看板模块基础权限 — L1/L2/L4/L5 通过 module_code 从 DB 动态读取。"""

    module_code = 'panel'


# ══════════════════════════════════════════════════════════
#  个人工作台卡片权限 Mixin（组合对应模块权限，统一管理）
# ══════════════════════════════════════════════════════════

class WorkspaceFormCardMixin(PanelAccessMixin):
    """个人工作台 - 表单卡片权限。

    门控链：PanelAccessMixin (L1/L2) → FormManagementAccessMixin (L1 module_code='form_management')
    用于「我提交的表单」卡片的可见性判断和数据查询的门控。
    """

    @classmethod
    def user_has_form_access(cls, user) -> bool:
        """检查用户是否有表单模块访问权限。"""
        from app_form_management.mixins import FormManagementAccessMixin
        return FormManagementAccessMixin.user_has_access(user)


class WorkspaceWorkflowCardMixin(PanelAccessMixin):
    """个人工作台 - 流程卡片权限。

    门控链：PanelAccessMixin (L1/L2) → WorkflowAccessMixin (L1 module_code='workflow')
    用于「我已发的流程」「待办任务」「已办任务」卡片的可见性判断和数据查询的门控。
    """

    @classmethod
    def user_has_workflow_access(cls, user) -> bool:
        """检查用户是否有流程模块访问权限。"""
        from app_workflow.mixins import WorkflowAccessMixin
        return WorkflowAccessMixin.user_has_access(user)
