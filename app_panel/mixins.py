from app_user.mixins import UnifiedAccessMixin

class PanelAccessMixin(UnifiedAccessMixin):
    """工作台看板模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'panel'
