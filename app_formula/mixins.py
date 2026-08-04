from app_user.mixins import UnifiedAccessMixin

class FormulaAccessMixin(UnifiedAccessMixin):
    """实验配方模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'formula'
    module_name = '实验配方库'
    user_link_fields = ['creator']
