from django.db import models
from django.conf import settings
from app_process.models import AbstractExtrusionParams


class ExtrusionTask(AbstractExtrusionParams):
    """挤出任务 — 记录实际运行参数，字段结构继承自 AbstractExtrusionParams"""

    class Status(models.TextChoices):
        PENDING = 'PENDING', '待生产'
        IN_PROGRESS = 'IN_PROGRESS', '挤出中'
        COMPLETED = 'COMPLETED', '已完成'

    production_order = models.OneToOneField('app_trial_production.ProductionOrder', on_delete=models.CASCADE, related_name='extrusion_task', verbose_name="关联工单")

    # 操作员
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="挤出操作员", related_name='extrusion_tasks')

    # ---- 状态与时间 ----
    status = models.CharField("任务状态", max_length=20, choices=Status.choices, default=Status.PENDING)
    remark = models.TextField("备注", blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="记录人", related_name='extrusion_recorded_tasks')
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    # ---- 颗粒分拨 ----
    pellet_split_completed = models.BooleanField("颗粒分拨已完成", default=False)

    class Meta:
        verbose_name = "挤出任务"
        verbose_name_plural = "挤出任务"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.production_order.code} 挤出任务 [{self.get_status_display()}]"

    @property
    def status_label(self):
        return self.Status(self.status).label

    @property
    def status_css_class(self):
        return {
            self.Status.PENDING: 'bg-secondary-lt',
            self.Status.IN_PROGRESS: 'bg-azure-lt',
            self.Status.COMPLETED: 'bg-green-lt',
        }.get(self.status, 'bg-secondary-lt')

    @property
    def pellet_split_label(self):
        return '已分拨' if self.pellet_split_completed else '未分拨'

    @property
    def pellet_split_css_class(self):
        return 'bg-green-lt' if self.pellet_split_completed else 'bg-secondary-lt'
