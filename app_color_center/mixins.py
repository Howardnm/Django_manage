from app_user.mixins import UnifiedAccessMixin


class ColorCenterAccessMixin(UnifiedAccessMixin):
    """配色中心权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    操作员数据视野放宽逻辑已移除——角色通过 ModuleAccessConfig 分配后自然有权访问。
    """

    module_code = 'color_center'
    module_name = '材料配色中心'
    user_link_fields = ['operator']
