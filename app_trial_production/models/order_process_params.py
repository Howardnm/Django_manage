from django.db import models

from app_process.models import AbstractExtrusionParams


class OrderProcessParams(AbstractExtrusionParams):
    """工单工艺参数 — 创建工单时从工艺方案预填，可再改。挤出任务只读这些值。"""

    production_order = models.OneToOneField('app_trial_production.ProductionOrder', on_delete=models.CASCADE, related_name='process_params', verbose_name="关联工单")

    class Meta:
        verbose_name = "工单工艺参数"
        verbose_name_plural = "工单工艺参数"

    def __str__(self):
        return f"{self.production_order.code} 工艺参数"
