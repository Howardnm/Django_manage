"""
附件配置注册中心

全局存储 model_class → AttachmentConfig 的映射。
不使用 ContentType 作为 key（避免 ready() 中迁移时序问题），
运行时按需解析 ContentType。
"""
from typing import Dict, Optional

from django.contrib.contenttypes.models import ContentType

from .configs import AttachmentConfig

# model_class → AttachmentConfig
_registry: Dict[type, AttachmentConfig] = {}


def register_attachment(config: AttachmentConfig) -> None:
    """
    注册附件配置。

    调用时机：各业务模块 apps.py 的 ready() 方法中。

    Example:
        register_attachment(AttachmentConfig(
            parent_model=ProjectRepository,
            access_mixin=RepositoryAccessMixin,
            view_permission='app_repository.view_projectrepository',
            add_permission='app_repository.change_projectrepository',
            delete_permission='app_repository.change_projectrepository',
            categories=[...],
            permission_parent_chain='project',
            group_field='node_id',
        ))
    """
    if config.parent_model in _registry:
        raise ValueError(
            f"AttachmentConfig for {config.parent_model.__name__} "
            f"is already registered."
        )
    _registry[config.parent_model] = config


def get_attachment_config_for_model(parent_model_class: type) -> Optional[AttachmentConfig]:
    """根据父模型类获取附件配置。"""
    return _registry.get(parent_model_class)


def get_attachment_config_for_ct(content_type: ContentType) -> AttachmentConfig:
    """
    运行时根据 ContentType 查找对应的 AttachmentConfig。

    遍历注册表中的 model_class，匹配其 ContentType.id。
    首次调用时会触发 ContentType.objects.get_for_model()，
    但这是在运行时而非 ready() 阶段，避免了迁移时序问题。

    Raises:
        ValueError: 如果未注册该 ContentType 对应的配置
    """
    for model_cls, config in _registry.items():
        ct = ContentType.objects.get_for_model(model_cls)
        if ct.id == content_type.id:
            return config

    # 尝试通过 content_type.model_class() 直接匹配
    model_class = content_type.model_class()
    if model_class and model_class in _registry:
        return _registry[model_class]

    raise ValueError(
        f"No AttachmentConfig registered for ContentType "
        f"id={content_type.id} ({content_type.app_label}.{content_type.model}). "
        f"Call register_attachment() in the app's ready() method."
    )


def get_all_registered_configs() -> Dict[type, AttachmentConfig]:
    """返回所有已注册的配置（用于调试/管理）。"""
    return dict(_registry)
