from django.db import models
from django.conf import settings
from django.utils.functional import cached_property


class ColorMatchingTask(models.Model):
    """
    配色任务 — 与挤出任务并行执行。
    负责补充挤出调试好的色粉BOM，配色数据本身存储在 app_formula.ColorPowderBOM 中。
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', '待配色'
        IN_PROGRESS = 'IN_PROGRESS', '配色中'
        COMPLETED = 'COMPLETED', '已完成'
        NOT_REQUIRED = 'NOT_REQUIRED', '无需配色'

    production_order = models.OneToOneField(
        'app_trial_production.ProductionOrder',
        on_delete=models.CASCADE,
        related_name='color_task',
        verbose_name="关联工单",
    )

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="配色操作员",
        related_name='color_tasks',
    )

    status = models.CharField("任务状态", max_length=20, choices=Status.choices, default=Status.PENDING)
    remark = models.TextField("备注", blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "配色任务"
        verbose_name_plural = "配色任务"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.production_order.code} 配色任务 [{self.get_status_display()}]"

    @property
    def status_label(self):
        return self.Status(self.status).label

    @cached_property
    def needs_color_matching(self):
        """从工单配方明细中判断是否需要配色（缓存，实例生命周期内只查一次）"""
        return self.production_order.formula_details.filter(
            needs_color_matching=True).exists()

    @property
    def status_css_class(self):
        return {
            self.Status.PENDING: 'bg-orange-lt',
            self.Status.IN_PROGRESS: 'bg-azure-lt',
            self.Status.COMPLETED: 'bg-green-lt',
            self.Status.NOT_REQUIRED: 'bg-secondary-lt',
        }.get(self.status, 'bg-secondary-lt')
