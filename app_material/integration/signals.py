from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.db import transaction
from ..models.material import MaterialLibrary, ApplicationScenario, MaterialCharacteristic
from .webhooks import send_material_webhook

# --- 1. 物料主档变更监听 ---
@receiver(post_save, sender=MaterialLibrary)
def material_saved_handler(sender, instance, created, **kwargs):
    """物料创建或更新时触发同步"""
    event_type = 'material_created' if created else 'material_updated'
    transaction.on_commit(lambda: send_material_webhook(event_type, instance))

@receiver(post_delete, sender=MaterialLibrary)
def material_deleted_handler(sender, instance, **kwargs):
    """物料删除时触发同步"""
    send_material_webhook('material_deleted', instance)

# --- 2. 关联关系变更监听 (M2M) ---
# 当物料关联的场景、特征发生变化时，必须触发 material_updated
@receiver(m2m_changed, sender=MaterialLibrary.scenarios.through)
@receiver(m2m_changed, sender=MaterialLibrary.characteristics.through)
def material_relations_changed(sender, instance, action, **kwargs):
    """当物料的多对多关联关系发生任何变化时，触发 Webhook"""
    # 只有在 post_add, post_remove, post_clear 动作后才发送，避免中间过程产生碎片请求
    if action in ["post_add", "post_remove", "post_clear"]:
        transaction.on_commit(lambda: send_material_webhook('material_updated', instance))

# --- 3. 维度主数据变更监听 ---
@receiver(post_save, sender=ApplicationScenario)
@receiver(post_save, sender=MaterialCharacteristic)
def dimension_data_updated(sender, instance, created, **kwargs):
    """如果场景名称或特征名称修改了，通知手册系统刷新对应的镜像数据"""
    # 逻辑：对于每一个关联了此维度的物料，都触发一次同步
    # 或者简单起见，发送一个专门的 'dimension_updated' 信号
    # 这里我们采用更高效的策略：通知手册系统更新维度表
    event_type = 'dimension_updated'
    transaction.on_commit(lambda: send_material_webhook(event_type, instance))
