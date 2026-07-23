from app_user.mixins import UnifiedAccessMixin

class ProcessAccessMixin(UnifiedAccessMixin):
    """工艺模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'process'
    user_link_fields = ['creator']
