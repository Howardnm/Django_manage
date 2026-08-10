from app_user.mixins import UnifiedAccessMixin

class RawMaterialAccessMixin(UnifiedAccessMixin):
    """原材料模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'raw_material'
    module_name = '原材料/供应商'

    def check_edit_permission(self, obj):
        """原材料/供应商/类型为 SAP 同步的共享参考数据，无创建人归属概念。
        编辑权限由 L1 角色组（入门闸门）+ L3 change_* 权限码控制，无需对象级所有者校验。"""
        return  # 仅返回；L1/L3 已在准入阶段把关，此覆盖不放开角色组之外的访问
