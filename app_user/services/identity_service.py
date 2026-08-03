"""身份权限服务模块。从 DB 读取角色和分组配置，替代原 IdentityConfig 静态类。

缓存策略：
    - 使用 Django DatabaseCache 后端（rbac），所有 Worker 共享同一份缓存。
    - Admin 修改 RBAC 配置后通过 cache.delete() 清除缓存，跨 Worker 即时生效。
    - TTL 1 小时兜底：即使缓存失效逻辑遗漏，1 小时后自动过期。
    - 缓存不可用时自动降级为直接查 DB，不影响功能。

导出: IdentityService。
"""

import logging
from django.core.cache import caches

logger = logging.getLogger(__name__)

# ── 缓存 key 常量 ──────────────────────────────────────────
RBAC_CACHE_KEY_ROLES = 'rbac:roles'
RBAC_CACHE_KEY_GROUPS = 'rbac:groups'
RBAC_CACHE_KEY_MODULES = 'rbac:modules'
RBAC_TIMEOUT = 3600  # 1 小时 TTL


def _rbac_cache():
    """获取 rbac 缓存后端；若 rbac 后端不可用（如缓存表未创建），回退到 default。"""
    try:
        return caches['rbac']
    except Exception:
        return caches['default']


def _cache_get(cache, key):
    """安全地从缓存读取，缓存不可用时返回 None。"""
    try:
        return cache.get(key)
    except Exception as e:
        logger.warning("RBAC cache get('%s') failed: %s", key, e)
        return None


def _cache_set(cache, key, value, timeout):
    """安全地写入缓存，失败时静默忽略。"""
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as e:
        logger.warning("RBAC cache set('%s') failed: %s", key, e)


class IdentityService:
    """从 DB 读取角色、分组、模块权限配置（DatabaseCache 跨进程共享）。

    所有方法为静态方法，可在 mixin、view、context processor 中直接调用。
    配合 _resolve_config() 的单请求实例缓存，权限检查零额外 DB 开销。
    """

    # ── 角色 ──────────────────────────────────────────────

    @staticmethod
    def get_all_roles():
        """返回全部启用的 UserRole {code: {name, is_internal}} 字典。"""
        cache = _rbac_cache()
        roles = _cache_get(cache, RBAC_CACHE_KEY_ROLES)
        if roles is None:
            from app_user.models import UserRole
            roles = {
                r.code: {'name': r.name, 'is_internal': r.is_internal}
                for r in UserRole.objects.filter(is_active=True)
            }
            _cache_set(cache, RBAC_CACHE_KEY_ROLES, roles, timeout=RBAC_TIMEOUT)
        return roles

    @staticmethod
    def get_internal_role_codes():
        """返回所有内部角色的 code 列表（用于登录拦截等场景）。"""
        roles = IdentityService.get_all_roles()
        return [code for code, info in roles.items() if info['is_internal']]

    # ── 角色分组 ───────────────────────────────────────────

    @staticmethod
    def get_all_groups():
        """返回全部启用的 RoleGroup {code: [role_codes]} 字典。

        仅包含 is_active=True 的 RoleGroup 和其中 is_active=True 的 UserRole。
        """
        cache = _rbac_cache()
        groups = _cache_get(cache, RBAC_CACHE_KEY_GROUPS)
        if groups is None:
            from app_user.models import RoleGroup
            groups = {}
            for g in RoleGroup.objects.filter(is_active=True).prefetch_related('roles'):
                # 过滤停用的 UserRole（修复 #1c）
                groups[g.code] = list(
                    g.roles.filter(is_active=True).values_list('code', flat=True)
                )
            _cache_set(cache, RBAC_CACHE_KEY_GROUPS, groups, timeout=RBAC_TIMEOUT)
        return groups

    @staticmethod
    def get_role_codes(group_code):
        """返回指定 RoleGroup 包含的扁平化 role code 列表。"""
        groups = IdentityService.get_all_groups()
        return groups.get(group_code, [])

    # ── 模块权限配置 ───────────────────────────────────────

    @staticmethod
    def get_all_module_configs():
        """返回全部启用的 ModuleAccessConfig {module_code: config} 字典。

        仅包含 is_active=True 的 ModuleAccessConfig，
        其中仅计入 is_active=True 的 RoleGroup 和 UserRole。
        """
        cache = _rbac_cache()
        configs = _cache_get(cache, RBAC_CACHE_KEY_MODULES)
        if configs is None:
            from app_user.models import ModuleAccessConfig
            configs = {}
            for cfg in ModuleAccessConfig.objects.filter(is_active=True).prefetch_related(
                'role_groups__roles'
            ):
                role_codes = set()
                for rg in cfg.role_groups.filter(is_active=True):  # 修复 #1a: 过滤停用 RoleGroup
                    role_codes.update(
                        rg.roles.filter(is_active=True).values_list('code', flat=True)  # 修复 #1b: 过滤停用 UserRole
                    )
                configs[cfg.module_code] = {
                    'role_codes': list(role_codes),
                    'min_level': cfg.min_level,
                    'enforce_dept_isolation': cfg.enforce_dept_isolation,
                    'enforce_group_isolation': cfg.enforce_group_isolation,
                }
            _cache_set(cache, RBAC_CACHE_KEY_MODULES, configs, timeout=RBAC_TIMEOUT)
        return configs

    @staticmethod
    def get_module_config(module_code):
        """返回指定模块的完整权限配置 dict。

        Returns:
            {'role_codes': [...], 'min_level': int,
             'enforce_dept_isolation': bool, 'enforce_group_isolation': bool}
            若 module_code 不存在则返回空配置（配合 has_permission() 拒绝访问）。
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
        """清除所有 RBAC 缓存（Admin 保存/删除模型时调用）。

        使用 DatabaseCache 时，一次 delete_many 对所有 Worker 即时生效。
        缓存删除失败时静默忽略（下次 get 时自动从 DB 重新加载）。
        """
        cache = _rbac_cache()
        try:
            cache.delete_many([
                RBAC_CACHE_KEY_ROLES,
                RBAC_CACHE_KEY_GROUPS,
                RBAC_CACHE_KEY_MODULES,
            ])
        except Exception as e:
            logger.warning("RBAC cache delete_many failed: %s", e)