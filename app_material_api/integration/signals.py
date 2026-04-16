from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.db import transaction
from app_material.models.material import MaterialLibrary, ApplicationScenario, MaterialCharacteristic
from .webhooks import send_material_webhook, send_data_sync_webhook

# --- 1. 物料主档变更监听 ---
@receiver(post_save, sender=MaterialLibrary)
def material_saved_handler(sender, instance, created, **kwargs):
    event_type = 'material_created' if created else 'material_updated'
    transaction.on_commit(lambda: send_material_webhook(event_type, instance))

@receiver(post_delete, sender=MaterialLibrary)
def material_deleted_handler(sender, instance, **kwargs):
    send_material_webhook('material_deleted', instance)

# --- 2. 关联关系变更监听 (M2M) ---
@receiver(m2m_changed, sender=MaterialLibrary.scenarios.through)
@receiver(m2m_changed, sender=MaterialLibrary.characteristics.through)
def material_relations_changed(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        transaction.on_commit(lambda: send_material_webhook('material_updated', instance))

# --- 3. 维度主数据变更监听 ---
@receiver(post_save, sender=ApplicationScenario)
@receiver(post_save, sender=MaterialCharacteristic)
def dimension_data_updated(sender, instance, created, **kwargs):
    # 构建维度更新事件
    data = {'id': instance.id, 'name': instance.name}
    data['model'] = 'scenario' if 'Scenario' in instance.__class__.__name__ else 'characteristic'
    transaction.on_commit(lambda: send_data_sync_webhook('dimension_updated', data['model'], data))
