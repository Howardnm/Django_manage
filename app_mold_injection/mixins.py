from app_user.mixins import UnifiedAccessMixin


class InjectionTaskAccessMixin(UnifiedAccessMixin):
    """注塑任务权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    操作员数据视野放宽逻辑已移除——角色通过 ModuleAccessConfig 分配后自然有权访问。
    """

    module_code = 'mold_injection.task'
    module_name = '注塑任务'
    module_description = '注塑任务。角色组配注塑操作员；需 view/change_injectiontask。'
    user_link_fields = ['operator']


class MoldManageAccessMixin(UnifiedAccessMixin):
    """模具台账管理权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    模具台账不做 L4/L5 数据隔离：MoldType 无所有者字段，对象级/数据隔离不适用，
    纯靠模块准入（L1 角色 + L2 等级 + 视图层 L3 权限码）把关。
    """

    module_code = 'mold_injection.mold'
    module_name = '模具台账'
    module_description = '模具台账。不做 L4/L5 隔离，纯模块准入；需 view/add/change_moldtype。'
