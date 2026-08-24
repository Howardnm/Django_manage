from app_user.mixins import UnifiedAccessMixin

class ProcessAccessMixin(UnifiedAccessMixin):
    """工艺模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'process'
    module_name = '生产工艺库'
    module_description = '生产工艺库。按创建人(creator)隔离。'
    user_link_fields = ['creator']
