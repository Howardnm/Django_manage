from app_user.mixins import UnifiedAccessMixin

class BasicResearchAccessMixin(UnifiedAccessMixin):
    """预研项目模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'basic_research'
    module_name = '基础预研中心'
    user_link_fields = ['manager']
