"""app_material 信号处理 — 材料库对外数据缓存失效。

此模块通过 Django signals 统一覆盖所有变更路径（视图、Admin、shell、管理命令等）：
    post_save / post_delete — 材料主表、维度表、物性子表、附件
    m2m_changed            — MaterialLibrary.scenarios / characteristics 的 M2M 关系变更

form.save() 的 save_m2m() 写入 M2M 关系时不会触发 post_save，
必须由 m2m_changed 兜底，否则 M2M 变更会静默地停留在缓存中。
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver

from app_attachment.models import Attachment
from .models.material import (
    MaterialLibrary, MaterialType, ApplicationScenario, MaterialCharacteristic,
    MetricCategory, TestConfig, MaterialDataPoint,
)
from .services.material_cache import MaterialCache


@receiver([post_save, post_delete], sender=MaterialLibrary)
@receiver([post_save, post_delete], sender=MaterialType)
@receiver([post_save, post_delete], sender=ApplicationScenario)
@receiver([post_save, post_delete], sender=MaterialCharacteristic)
@receiver([post_save, post_delete], sender=MetricCategory)
@receiver([post_save, post_delete], sender=TestConfig)
@receiver([post_save, post_delete], sender=MaterialDataPoint)
def invalidate_material_cache(sender, instance, **kwargs):
    """材料主表 / 维度表 / 物性子表变更时清除缓存。"""
    # post_save 信号带 created 布尔值；post_delete 无 created 键
    if 'created' in kwargs:
        action = 'post_create' if kwargs['created'] else 'post_update'
    else:
        action = 'post_delete'
    MaterialCache.invalidate(trigger=f"{sender.__name__}.{action}")


@receiver(m2m_changed, sender=MaterialLibrary.scenarios.through)
@receiver(m2m_changed, sender=MaterialLibrary.characteristics.through)
def invalidate_material_cache_m2m(sender, instance, action, **kwargs):
    """MaterialLibrary.scenarios / characteristics 的 M2M 关系变更时清除缓存。

    m2m_changed 对每次操作触发 pre/post 两轮，仅处理 post_* 实际生效的动作。
    """
    if action in ('post_add', 'post_remove', 'post_clear'):
        model_name = instance.__class__.__name__
        MaterialCache.invalidate(trigger=f"{model_name}.{action}")


def _attachment_targets_material(instance):
    """判断附件是否挂在 MaterialLibrary 上（附件被多业务复用，仅材料附件失效）。"""
    return instance.content_type_id == ContentType.objects.get_for_model(MaterialLibrary).id


@receiver([post_save, post_delete], sender=Attachment)
def invalidate_material_cache_on_attachment(sender, instance, **kwargs):
    """材料附件（TDS/MSDS/RoHS 等）变更时清除缓存；软删走 post_save 已覆盖。"""
    if not _attachment_targets_material(instance):
        return
    if 'created' in kwargs:
        action = 'post_create' if kwargs['created'] else 'post_update'
    else:
        action = 'post_delete'
    MaterialCache.invalidate(trigger=f"Attachment.{action}")
