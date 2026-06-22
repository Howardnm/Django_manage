from django.db import models
from django.conf import settings


class TestingTask(models.Model):
    """测试任务 — 关联排产工单，填写测试项×配方矩阵结果"""

    class Status(models.TextChoices):
        PENDING = 'PENDING', '待测试'
        IN_PROGRESS = 'IN_PROGRESS', '测试中'
        COMPLETED = 'COMPLETED', '已完成'
        RESULTS_WRITTEN_BACK = 'RESULTS_WRITTEN_BACK', '已回写'

    production_order = models.ForeignKey(
        'app_trial_production.ProductionOrder',
        on_delete=models.CASCADE,
        related_name='testing_tasks',
        verbose_name="关联工单",
    )
    test_items = models.ManyToManyField(
        'app_material.TestConfig',
        blank=True,
        verbose_name="测试项目",
        related_name="trial_testing_tasks",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="测试员",
        related_name='assigned_testing_tasks',
    )

    status = models.CharField("任务状态", max_length=30, choices=Status.choices, default=Status.PENDING)
    remark = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "测试任务"
        verbose_name_plural = "测试任务"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.production_order.code} 测试任务 [{self.get_status_display()}]"

    @property
    def status_label(self):
        return self.Status(self.status).label

    @property
    def status_css_class(self):
        return {
            self.Status.PENDING: 'bg-secondary-lt',
            self.Status.IN_PROGRESS: 'bg-yellow-lt',
            self.Status.COMPLETED: 'bg-green-lt',
            self.Status.RESULTS_WRITTEN_BACK: 'bg-info-lt',
        }.get(self.status, 'bg-secondary-lt')


class TrialTestResult(models.Model):
    """试验测试中间结果 — 审批通过后回写到 FormulaTestResult"""
    testing_task = models.ForeignKey(
        TestingTask,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='test_results',
        verbose_name="关联测试任务",
    )
    test_config = models.ForeignKey(
        'app_material.TestConfig',
        on_delete=models.PROTECT,
        related_name='trial_test_results',
        verbose_name="测试项目",
    )
    formula = models.ForeignKey(
        'app_formula.LabFormula',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='trial_test_results_by_formula',
        verbose_name="对应配方版本",
        help_text="多配方排产时，每个配方版本独立填写测试结果",
    )
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3, null=True, blank=True)
    value_text = models.CharField("文本结果", max_length=50, blank=True)
    test_date = models.DateField("测试日期", null=True, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)
    is_written_back = models.BooleanField("已回写配方", default=False)

    class Meta:
        verbose_name = "试验测试结果"
        verbose_name_plural = "试验测试结果"
        constraints = [
            models.UniqueConstraint(
                fields=['testing_task', 'test_config', 'formula'],
                name='unique_test_result_per_task_config_formula',
            ),
        ]
        ordering = ['test_config__category__order', 'test_config__order']
