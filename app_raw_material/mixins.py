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


class RawMaterialPickerAccessMixin(UnifiedAccessMixin):
    """原材料搜索选择器权限管控。

    独立于 RawMaterialAccessMixin：允许在不授予「原材料」模块完整权限的情况下，
    单独授予搜索选择器的使用权限。L1 角色白名单从
    ModuleAccessConfig(module_code='raw_material_picker') 动态读取。
    """

    module_code = 'raw_material_picker'
    module_name = '原材料搜索选择器'
    user_link_fields = []  # RawMaterial 无所有者字段，避免 access_filter 回退默认 'manager' 触发 FieldError
