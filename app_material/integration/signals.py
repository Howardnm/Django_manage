from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.db import transaction
from ..models.material import MaterialLibrary, ApplicationScenario, MaterialCharacteristic
from .webhooks import send_material_webhook

# --- 1. 物料主档变更监听 ---
@receiver(post_save, sender=MaterialLibrary)
def material_saved_handler(sender, instance, created, **kwargs):
    """物料创建或更新时触发"""
    event_type = 'material_created' if created else 'material_updated'
    # 使用 on_commit 确保在数据库事务提交后才发送 Webhook
    transaction.on_commit(lambda: send_material_webhook(event_type, instance))

@receiver(post_delete, sender=MaterialLibrary)
def material_deleted_handler(sender, instance, **kwargs):
    """物料删除时触发"""
    send_material_webhook('material_deleted', instance)

# --- 2. 关联关系变更监听 (M2M) ---
@receiver(m2m_changed, sender=MaterialLibrary.scenarios.through)
@receiver(m2m_changed, sender=MaterialLibrary.characteristics.through)
def material_relations_changed(sender, instance, action, **kwargs):
    """当物料关联的场景或特征发生变化时，也触发更新"""
    if action in ["post_add", "post_remove", "post_clear"]:
        transaction.on_commit(lambda: send_material_webhook('material_updated', instance))

# --- 3. 维度数据变更监听 (场景/特征名称修改) ---
@receiver(post_save, sender=ApplicationScenario)
@receiver(post_save, sender=MaterialCharacteristic)
def dimension_data_updated(sender, instance, created, **kwargs):
    """如果场景或特征的名称改了，通知手册系统同步镜像"""
    # 逻辑：查找关联了该场景/特征的所有物料并触发更新（或者发送专门的维度更新事件）
    # 这里我们简化处理：发送一个 material_updated 事件给受影响的物料
    # 或者发送一个专门的 'dimension_updated' 事件让手册系统全量刷新
    # 为了极致性能，我们告诉手册系统：有基础维度变了，请刷新缓存
    pass # 后续可根据需要扩展专门的全局刷新 Webhook
