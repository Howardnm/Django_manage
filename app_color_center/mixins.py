from app_user.mixins import UnifiedAccessMixin


class ColorCenterAccessMixin(UnifiedAccessMixin):
    """配色中心基础准入管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    对象级规则统一为「无」——由模块准入（L1 角色 + 视图层 L3 权限码）把关。
    """

    module_code = 'color_center'
    module_name = '材料配色中心'
    user_link_fields = ['operator']


class ColorCenterReadMixin(ColorCenterAccessMixin):
    """配色中心「读」侧准入。

    继承基础准入（module_code='color_center'），当前无额外权限规则，
    作为读写分层的入口点，便于日后对读操作单独扩展权限管控。
    """


class ColorCenterWriteMixin(ColorCenterReadMixin):
    """配色中心「写」侧准入 —— 单独声明 module_code 供 sync_rbac_modules 注册、独立控权。"""

    module_code = 'color_center.write'
    module_name = '材料配色中心-填写'
    user_link_fields = ['operator']