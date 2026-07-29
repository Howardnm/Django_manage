import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import RawMaterial
from app_formula.models import FormulaBOM

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=RawMaterial)
def capture_old_price(sender, instance, **kwargs):
    """
    在保存前，获取旧的价格，以便后续对比
    """
    if instance.pk:
        try:
            old_instance = RawMaterial.objects.get(pk=instance.pk)
            instance._old_latest_price = old_instance._latest_price
        except RawMaterial.DoesNotExist:
            instance._old_latest_price = None
    else:
        instance._old_latest_price = None

@receiver(post_save, sender=RawMaterial)
def update_formula_costs(sender, instance, created, **kwargs):
    """
    当原材料价格发生变化时，自动更新所有关联配方的预测成本
    """
    # 检查价格是否发生变化
    old_price = getattr(instance, '_old_latest_price', None)
    new_price = instance._latest_price

    if old_price != new_price:
        logger.info("RawMaterial [%s] price change: %s -> %s, updating formulas...",
                     instance.name, old_price, new_price)

        # 1. 找到所有使用了该原材料的 BOM 行
        # select_related('formula') 优化查询
        boms = FormulaBOM.objects.filter(raw_material=instance).select_related('formula')

        # 2. 获取所有受影响的配方 (去重)
        formulas = set(bom.formula for bom in boms)

        # 3. 逐个重新计算成本
        count = 0
        for formula in formulas:
            formula.calculate_cost()
            count += 1

        logger.info("Updated %d formulas for raw material [%s] price change.", count, instance.name)
