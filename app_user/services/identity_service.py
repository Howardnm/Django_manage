"""身份权限服务模块。从 DB 读取角色和分组配置，替代原 IdentityConfig 静态类。

提供模块级内存缓存，Admin 修改配置后通过 invalidate_cache() 刷新。

导出: IdentityService。
"""

# 模块级内存缓存（无需配置 Django cache backend）
_cache_roles = None
_cache_groups = None
_cache_modules = None


class IdentityService:
    """从 DB 读取角色、分组、模块权限配置（模块级缓存）。

    所有方法为静态方法，可在 mixin、view、context processor 中直接调用。
    配合 _resolve_config() 的单请求实例缓存，权限检查零 DB 开销。
    """

    # ── 角色 ──────────────────────────────────────────────

    @staticmethod
    def get_all_roles():
        """返回全部启用的 UserRole {code: {name, is_internal}} 字典。"""
        global _cache_roles
        if _cache_roles is None:
            from app_user.models import UserRole
            _cache_roles = {
                r.code: {'name': r.name, 'is_internal': r.is_internal}
                for r in UserRole.objects.filter(is_active=True)
            }
        return _cache_roles

    @staticmethod
    def get_internal_role_codes():
        """返回所有内部角色的 code 列表（用于登录拦截等场景）。"""
        roles = IdentityService.get_all_roles()
        return [code for code, info in roles.items() if info['is_internal']]

    # ── 角色分组 ───────────────────────────────────────────

    @staticmethod
    def get_all_groups():
        """返回全部启用的 RoleGroup {code: [role_codes]} 字典。"""
        global _cache_groups
        if _cache_groups is None:
            from app_user.models import RoleGroup
            _cache_groups = {}
            for g in RoleGroup.objects.filter(is_active=True).prefetch_related('roles'):
                _cache_groups[g.code] = list(g.roles.values_list('code', flat=True))
        return _cache_groups

    @staticmethod
    def get_role_codes(group_code):
        """返回指定 RoleGroup 包含的扁平化 role code 列表。"""
        groups = IdentityService.get_all_groups()
        return groups.get(group_code, [])

    # ── 模块权限配置 ───────────────────────────────────────

    @staticmethod
    def get_all_module_configs():
        """返回全部启用的 ModuleAccessConfig {module_code: config} 字典。"""
        global _cache_modules
        if _cache_modules is None:
            from app_user.models import ModuleAccessConfig
            _cache_modules = {}
            for cfg in ModuleAccessConfig.objects.filter(is_active=True).prefetch_related(
                'role_groups__roles'
            ):
                role_codes = set()
                for rg in cfg.role_groups.all():
                    role_codes.update(rg.roles.values_list('code', flat=True))
                _cache_modules[cfg.module_code] = {
                    'role_codes': list(role_codes),
                    'min_level': cfg.min_level,
                    'enforce_dept_isolation': cfg.enforce_dept_isolation,
                    'enforce_group_isolation': cfg.enforce_group_isolation,
                }
        return _cache_modules

    @staticmethod
    def get_module_config(module_code):
        """返回指定模块的完整权限配置 dict。

        Returns:
            {'role_codes': [...], 'min_level': int,
             'enforce_dept_isolation': bool, 'enforce_group_isolation': bool}
            若 module_code 不存在则返回空配置（拒绝所有人访问）。
        """
        configs = IdentityService.get_all_module_configs()
        return configs.get(module_code, {
            'role_codes': [],
            'min_level': 1,
            'enforce_dept_isolation': True,
            'enforce_group_isolation': False,
        })

    @staticmethod
    def get_module_role_codes(module_code):
        """返回指定模块允许的所有 role code 列表（扁平化）。"""
        cfg = IdentityService.get_module_config(module_code)
        return cfg['role_codes']

    # ── 缓存管理 ───────────────────────────────────────────

    @staticmethod
    def invalidate_cache():
        """清除所有模块级缓存（Admin 保存/删除模型时调用）。"""
        global _cache_roles, _cache_groups, _cache_modules
        _cache_roles = None
        _cache_groups = None
        _cache_modules = None
