"""app_user 信号处理 — RBAC 缓存失效。

此模块通过 Django signals 统一覆盖所有变更路径（Admin、shell、管理命令、数据迁移等）：
    post_save / post_delete — 5 个 RBAC 模型的增删改
    m2m_changed            — RoleGroup.roles / ModuleAccessConfig.role_groups 的 M2M 关系变更

Admin 的 save_related() 写入 filter_horizontal 的 M2M 关系时不会触发 post_save，
必须由 m2m_changed 兜底，否则 M2M 变更会静默地停留在缓存中。
"""

from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver

from .models import UserRole, RoleGroup, ModuleAccessConfig, SidebarModule, SidebarSubItem
from .services.identity_service import IdentityService


@receiver([post_save, post_delete], sender=UserRole)
@receiver([post_save, post_delete], sender=RoleGroup)
@receiver([post_save, post_delete], sender=ModuleAccessConfig)
@receiver([post_save, post_delete], sender=SidebarModule)
@receiver([post_save, post_delete], sender=SidebarSubItem)
def invalidate_rbac_cache(sender, instance, **kwargs):
    """UserRole / RoleGroup / ModuleAccessConfig / SidebarModule / SidebarSubItem 变更时清除缓存。"""
    # post_save 信号带 created 布尔值；post_delete 无 created 键
    if 'created' in kwargs:
        action = 'post_create' if kwargs['created'] else 'post_update'
    else:
        action = 'post_delete'
    IdentityService.invalidate_cache(trigger=f"{sender.__name__}.{action}")


@receiver(m2m_changed, sender=RoleGroup.roles.through)
@receiver(m2m_changed, sender=ModuleAccessConfig.role_groups.through)
def invalidate_rbac_cache_m2m(sender, instance, action, **kwargs):
    """RoleGroup.roles / ModuleAccessConfig.role_groups 的 M2M 关系变更时清除缓存。

    m2m_changed 对每次操作触发 pre/post 两轮，仅处理 post_* 实际生效的动作。
    """
    if action in ('post_add', 'post_remove', 'post_clear'):
        model_name = instance.__class__.__name__
        IdentityService.invalidate_cache(trigger=f"{model_name}.{action}")
