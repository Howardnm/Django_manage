from django.db import models
from django.conf import settings


class InjectionMoldingOrder(models.Model):
    """
    注塑工单 - 一张排产单只关联一张注塑工单，一张工单可含多种模具需求。
    两种来源渠道均由研发工程师决定。
    """
    STATUS_CHOICES = [
        ('PENDING', '待生产'),
        ('IN_PROGRESS', '注塑中'),
        ('COMPLETED', '已完成'),
    ]

    # 渠道A: 随排产单下
    production_order = models.OneToOneField(
        'app_trial_production.ProductionOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='injection_order',
        verbose_name="关联排产单", help_text="一张排产单只对应一张注塑工单")
    sample_split = models.ForeignKey(
        'app_trial_production.SampleSplit', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="物料来源(分拨)",
        help_text="排产样品分拨到注塑房的物料来源")

    # 渠道B: 独立注塑 — 从样品库已有样品取料
    sample_inventory = models.ForeignKey(
        'app_trial_production.SampleInventory', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='injection_orders',
        verbose_name="物料来源(样品库)", help_text="从样品库取料注塑打样")

    # 人员与工艺
    injection_params_note = models.TextField("注塑工艺备注", blank=True)
    assigned_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='injection_molding_orders',
        verbose_name="注塑操作员")

    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='PENDING')
    remark = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "注塑工单"
        verbose_name_plural = "注塑工单"
        ordering = ['-created_at']


class MoldRequirement(models.Model):
    """注塑工单的模具需求明细 — 一张工单可含多种模具"""
    injection_order = models.ForeignKey(
        InjectionMoldingOrder, on_delete=models.CASCADE,
        related_name='mold_requirements', verbose_name="所属注塑工单")
    mold = models.ForeignKey(
        'app_trial_production.MoldType', on_delete=models.PROTECT, verbose_name="使用模具")
    formula = models.ForeignKey(
        'app_formula.LabFormula', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="对应配方版本",
        help_text="多配方排产时指定对应配方；为空则适用于所有配方")
    specimen_quantity = models.PositiveIntegerField("计划制样数量")
    order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        verbose_name = "模具需求明细"
        verbose_name_plural = "模具需求明细"
        ordering = ['order']


class SpecimenInventory(models.Model):
    """样条产出记录 - 以注塑工单为整体，每种模具一行"""
    STATUS_CHOICES = [
        ('AVAILABLE', '可用'),
        ('SENT_TO_TESTING', '已送测试'),
        ('TESTED', '已测试'),
        ('DISCARDED', '已废弃'),
    ]
    injection_order = models.ForeignKey(
        InjectionMoldingOrder, on_delete=models.CASCADE,
        related_name='specimens', verbose_name="所属注塑工单")
    mold = models.ForeignKey(
        'app_trial_production.MoldType', on_delete=models.PROTECT, verbose_name="模具")
    quantity_produced = models.PositiveIntegerField("实际产出数量")
    quantity_qualified = models.PositiveIntegerField("合格数量",
        help_text="可送测试中心的数量")
    storage_location = models.CharField("存放位置", max_length=100, blank=True)
    batch_label = models.CharField("批次标签", max_length=50, blank=True)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "样条产出"
        verbose_name_plural = "样条库存"
        ordering = ['mold__mold_code']
