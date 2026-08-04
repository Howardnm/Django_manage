from app_user.mixins import UnifiedAccessMixin


class PanelAccessMixin(UnifiedAccessMixin):
    """工作台看板模块基础权限 — L1/L2/L4/L5 通过 module_code 从 DB 动态读取。"""

    module_code = 'panel'
    module_name = '看板工作台'


class HomeAccessMixin(UnifiedAccessMixin):
    """系统首页基础权限 — 独立 module_code='home'，与看板工作台（panel）权限解耦。

    L1/L2: HomeAccessMixin (module_code='home') 从 DB 读取。
    L3: 显式声明 [] — 本页为零数据库查询的纯静态页面，无适用 L3 权限码。

    注意：module_code='home' 的 ModuleAccessConfig 需通过
    python manage.py sync_rbac_modules 创建，并在 Admin 中配置 role_groups；
    未配置时 fail-closed（仅超管可访问首页）。
    """

    module_code = 'home'
    module_name = '系统首页'
    permission_required = []  # 纯静态页面，零数据查询


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
