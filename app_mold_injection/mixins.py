from app_user.mixins import UnifiedAccessMixin


class InjectionTaskAccessMixin(UnifiedAccessMixin):
    """注塑任务权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    操作员数据视野放宽逻辑已移除——角色通过 ModuleAccessConfig 分配后自然有权访问。
    """

    module_code = 'mold_injection.task'
    user_link_fields = ['operator']


class MoldManageAccessMixin(UnifiedAccessMixin):
    """模具台账管理权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'mold_injection.mold'
