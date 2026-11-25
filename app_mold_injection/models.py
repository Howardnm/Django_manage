from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q, CheckConstraint


class MoldType(models.Model):
    """
    模具台账 — 管理试验用模具的基本信息与状态。
    """

    class MoldTypeChoices(models.TextChoices):
        TEST_SPECIMEN = 'TEST_SPECIMEN', '测试样条模具'
        FINISHED_PART = 'FINISHED_PART', '成品模具'
        PROTOTYPE = 'PROTOTYPE', '原型模具'
        TOOLING = 'TOOLING', '工装夹具'
        OTHER = 'OTHER', '其他'

    class Standard(models.TextChoices):
        ISO = 'ISO', 'ISO 标准'
        ASTM = 'ASTM', 'ASTM 标准'
        GB = 'GB', 'GB 标准'
        OTHER = 'OTHER', '其他标准'

    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', '可用'
        MAINTENANCE = 'MAINTENANCE', '维护中'
        RETIRED = 'RETIRED', '已退役'

    name = models.CharField("模具名称", max_length=100)
    mold_code = models.CharField("模具编号", max_length=50, unique=True)
    mold_type = models.CharField("模具类型", max_length=30, choices=MoldTypeChoices.choices)
    standard = models.CharField("模具标准", max_length=30, choices=Standard.choices)
    specimen_description = models.TextField("样条描述", blank=True)
    cavity_count = models.PositiveIntegerField("模腔数量", default=1)
    status = models.CharField("模具状态", max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    description = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "模具台账"
        verbose_name_plural = "模具台账"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.mold_code} — {self.name}"

    @property
    def status_css_class(self):
        return {
            self.Status.AVAILABLE: 'bg-green-lt',
            self.Status.MAINTENANCE: 'bg-yellow-lt',
            self.Status.RETIRED: 'bg-secondary-lt',
        }.get(self.status, 'bg-secondary-lt')


class InjectionTask(models.Model):
    """注塑任务 — 由排产工单在挤出并登记产量后触发。"""

    class Status(models.TextChoices):
        PENDING = 'PENDING', '未注塑'
        COMPLETED = 'COMPLETED', '已完成'

    production_order = models.OneToOneField('app_trial_production.ProductionOrder', on_delete=models.CASCADE, related_name='injection_task', verbose_name="关联排产单", help_text="一张排产单只对应一张注塑任务，删除工单时一并删除")
    # ---- 操作员与工艺 ----
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='injection_tasks', verbose_name="注塑操作员")
    injection_params_note = models.TextField("注塑工艺备注", blank=True)

    status = models.CharField("任务状态", max_length=20, choices=Status.choices, default=Status.PENDING)
    remark = models.TextField("备注", blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "注塑任务"
        verbose_name_plural = "注塑任务"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        order_code = self.production_order.code if self.production_order_id else '-'
        return f"{order_code} 注塑任务 [{self.get_status_display()}]"

    @property
    def status_css_class(self):
        return {
            self.Status.PENDING: 'bg-secondary-lt',
            self.Status.COMPLETED: 'bg-green-lt',
        }.get(self.status, 'bg-secondary-lt')


class MoldRequirement(models.Model):
    """模具需求 — 一行对应一个模具，配方版本注塑次数由 formula_details 子表存储"""
    injection_task = models.ForeignKey(InjectionTask, on_delete=models.CASCADE, null=True, blank=True, related_name='mold_requirements', verbose_name="所属注塑任务")
    production_order = models.ForeignKey('app_trial_production.ProductionOrder', on_delete=models.CASCADE, related_name='mold_requirements', verbose_name="关联工单", help_text="工单规划阶段即创建，injection_task 创建后关联")
    mold = models.ForeignKey(MoldType, on_delete=models.PROTECT, related_name='mold_requirements', verbose_name="使用模具")
    order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        verbose_name = "模具需求"
        verbose_name_plural = "模具需求"
        ordering = ['order']
        constraints = [
            CheckConstraint(
                condition=Q(production_order__isnull=False),
                name='mold_req_has_production_order',
            ),
        ]

    def clean(self):
        super().clean()
        # production_order 不可空。创建页表单不包含该字段，空值只出现在未保存的表单实例上，
        # 落库由 _save_mold_matrix() 传入工单。此处只校验：有注塑任务时工单不能为空。
        if self.injection_task_id and not self.production_order_id:
            raise ValidationError('关联注塑任务时，工单不能为空')

    def __str__(self):
        total = sum(
            d.specimen_quantity for d in self.formula_details.all()
        ) if self.pk else 0
        return f"{self.mold.name} — {total} 次"


class MoldRequirementFormulaDetail(models.Model):
    """模具需求-配方明细 — 每个配方版本的注塑次数"""
    mold_requirement = models.ForeignKey(MoldRequirement, on_delete=models.CASCADE, related_name='formula_details', verbose_name="所属模具需求")
    formula = models.ForeignKey('app_formula.LabFormula', on_delete=models.PROTECT, null=True, blank=True, verbose_name="对应配方版本", help_text="排产工单下的配方版本", )
    specimen_quantity = models.PositiveIntegerField("计划制样数量", default=0)

    class Meta:
        verbose_name = "模具需求-配方明细"
        verbose_name_plural = "模具需求-配方明细"
        constraints = [
            models.UniqueConstraint(
                fields=['mold_requirement', 'formula'],
                name='uq_mold_req_formula',
            ),
        ]

    def __str__(self):
        if self.formula_id:
            return f"{self.mold_requirement.mold.name} × v{self.formula.version} — {self.specimen_quantity} 次"
        return f"{self.mold_requirement.mold.name} — {self.specimen_quantity} 次（通用）"
