"""通用权限 Mixin 模块。

遵循 L1~L5 权限规范，继承 UnifiedAccessMixin 复用全套权限逻辑。
权限由超管在 Admin 后台通过 ModuleAccessConfig 动态配置。

导出: InternalUserRequiredMixin。
"""

from app_user.mixins import UnifiedAccessMixin


class InternalUserRequiredMixin(UnifiedAccessMixin):
    """通用 API 视图权限控制 Mixin，继承 UnifiedAccessMixin 复用 L1~L5 安全模型。

    权限来源（优先级从高到低）：
        1. 超管 → 直接放行
        2. ModuleAccessConfig (DB) 已配置 → 走父类完整 L1→L2→L3 检查
        3. 回退规则 → 未配置时，检查 user.user_type.is_internal

    module_code 已在 Mixin 中声明，子类无需重复声明：
        class UserTreeAPIView(InternalUserRequiredMixin, View):
            pass
    """

    module_code = 'common.user_tree'

    # 通用 API 视图不涉及 L4/L5 数据隔离
    enforce_dept_isolation = False
    enforce_group_isolation = False

    def has_permission(self):
        """准入判定：超管已配置 → 走父类 L1→L2→L3；未配置 → 回退 is_internal。

        修复 A1: 已配置时调用 super().has_permission() 补全 L2/L3 检查。
        修复 E3: 已配置但无 role_groups 时拒绝访问（而非回退）。
        """
        user = self.request.user

        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        cfg = self._resolve_config()
        role_codes = cfg['role_codes']

        if role_codes:
            # 超管已配置 L1 角色白名单 → 走父类完整 L1→L2→L3 检查
            return super().has_permission()
        else:
            # role_codes 为空：检查是否已有 ModuleAccessConfig 记录
            from app_user.services.identity_service import IdentityService
            configs = IdentityService.get_all_module_configs()

            if self.module_code in configs:
                # 已配置但无 role_groups → 拒绝所有非超管用户（修复 E3）
                return False

            # 未配置 ModuleAccessConfig → 回退到 is_internal 检查
            internal_codes = IdentityService.get_internal_role_codes()
            return user.user_type_id in internal_codes