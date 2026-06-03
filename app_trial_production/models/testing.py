from django.db import models
from django.conf import settings
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size


class TestingOrder(models.Model):
    """测试工单"""
    production_order = models.ForeignKey(
        'app_trial_production.ProductionOrder', on_delete=models.CASCADE,
        related_name='testing_orders', verbose_name="关联工单")
    test_items = models.ManyToManyField(
        'app_material.TestConfig', blank=True, verbose_name="测试项目",
        related_name="trial_testing_orders")
    specimens = models.ManyToManyField(
        'app_trial_production.SpecimenInventory', blank=True, verbose_name="使用样条",
        related_name="testing_orders")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="测试员",
        related_name='assigned_test_orders')
    STATUS_CHOICES = [
        ('PENDING', '待测试'),
        ('IN_PROGRESS', '测试中'),
        ('COMPLETED', '已完成'),
        ('RESULTS_WRITTEN_BACK', '已回写'),
    ]
    status = models.CharField("状态", max_length=30, choices=STATUS_CHOICES, default='PENDING')
    test_report = models.FileField("测试报告",
        upload_to=upload_file_path, null=True, blank=True,
        validators=[validate_file_size])
    remark = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "测试工单"
        verbose_name_plural = "测试工单"
        ordering = ['-created_at']


class TrialTestResult(models.Model):
    """试验测试中间结果 - 审批通过后回写到 FormulaTestResult"""
    testing_order = models.ForeignKey(
        TestingOrder, on_delete=models.CASCADE,
        related_name='test_results', verbose_name="关联测试工单")
    test_config = models.ForeignKey(
        'app_material.TestConfig', on_delete=models.PROTECT,
        verbose_name="测试项目")
    formula = models.ForeignKey(
        'app_formula.LabFormula', on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="对应配方版本",
        help_text="多配方排产时，每个配方版本独立填写测试结果")
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3, null=True, blank=True)
    value_text = models.CharField("文本结果", max_length=50, blank=True)
    test_date = models.DateField("测试日期", null=True, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)
    is_written_back = models.BooleanField("已回写配方", default=False)

    class Meta:
        verbose_name = "试验测试结果"
        verbose_name_plural = "试验测试结果"
        unique_together = ('testing_order', 'test_config', 'formula')
        ordering = ['test_config__category__order', 'test_config__order']
