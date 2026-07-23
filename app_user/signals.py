"""app_user 信号处理 — RBAC 缓存失效。

Admin 中通过 CacheInvalidatingMixin 覆盖 save/delete 方法实现失效；
此模块通过 Django signals 覆盖所有变更路径（shell、管理命令等）。
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import UserRole, RoleGroup, ModuleAccessConfig, SidebarModule
from .services.identity_service import IdentityService


@receiver([post_save, post_delete], sender=UserRole)
@receiver([post_save, post_delete], sender=RoleGroup)
@receiver([post_save, post_delete], sender=ModuleAccessConfig)
@receiver([post_save, post_delete], sender=SidebarModule)
def invalidate_rbac_cache(sender, instance, **kwargs):
    """UserRole / RoleGroup / ModuleAccessConfig / SidebarModule 变更时清除缓存。"""
    IdentityService.invalidate_cache()
