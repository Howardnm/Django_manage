from django.db import models
from django.conf import settings
from django.utils import timezone


class ProductionOrder(models.Model):
    """生产工单 - 试验排产的核心工单"""
    code = models.CharField("工单号", max_length=50, blank=True,
        help_text="自动生成，如：TP20250601-01")

    # 核心关联
    trial_code = models.CharField("实验单号", max_length=50, default='', db_index=True,
        help_text="对应 LabFormula.code，同批次配方共享")
    project = models.ForeignKey(
        'app_project.Project', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="关联项目", related_name='production_orders')
    project_node = models.ForeignKey(
        'app_project.ProjectNode', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="关联项目节点", related_name='production_orders')

    # 生产参数
    quantity_planned = models.DecimalField("计划产量(kg)", max_digits=10, decimal_places=2, default=25.0)
    quantity_actual = models.DecimalField("实际产量(kg)", max_digits=10, decimal_places=2, null=True, blank=True)

    # 工艺方案 (已内含机台、螺杆组合)
    process_profile = models.ForeignKey(
        'app_process.ProcessProfile', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="工艺方案")

    # 人员
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        verbose_name="创建人", related_name='created_production_orders')
    extruder_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="挤出操作员", related_name='extruder_orders')

    # 状态
    STATUS_CHOICES = [
        ('DRAFT', '草稿'),
        ('WORKFLOW_RUNNING', '流程中'),
        ('EXTRUDING', '挤出生产'),
        ('COLOR_POST', '产后配色BOM'),
        ('SAMPLE_SPLITTING', '样品分拨'),
        ('INJECTION_MOLDING', '注塑打样'),
        ('TESTING', '测试中'),
        ('COMPLETED', '已完成'),
        ('CANCELED', '已取消'),
    ]
    status = models.CharField("工单状态", max_length=30, choices=STATUS_CHOICES, default='DRAFT')

    # ---- Status groups ----
    HIDDEN_STATUSES = ['DRAFT', 'CANCELED']
    PRE_PRODUCTION_STATUSES = ['DRAFT', 'WORKFLOW_RUNNING']
    ACTIVE_STATUSES = ['WORKFLOW_RUNNING', 'EXTRUDING', 'COLOR_POST',
                       'SAMPLE_SPLITTING', 'INJECTION_MOLDING', 'TESTING']
    EXTRUSION_READY_STATUSES = ['EXTRUDING', 'COLOR_POST', 'SAMPLE_SPLITTING',
                                'INJECTION_MOLDING', 'TESTING', 'COMPLETED']
    POST_EXTRUSION_STATUSES = ['COLOR_POST', 'SAMPLE_SPLITTING',
                               'INJECTION_MOLDING', 'TESTING', 'COMPLETED']

    STATUS_FLOW_ORDER = ['DRAFT', 'WORKFLOW_RUNNING', 'EXTRUDING', 'COLOR_POST',
                         'SAMPLE_SPLITTING', 'INJECTION_MOLDING', 'TESTING', 'COMPLETED']

    STATUS_CSS_MAP = {
        'DRAFT': 'bg-secondary-lt',
        'WORKFLOW_RUNNING': 'bg-purple-lt',
        'EXTRUDING': 'bg-azure-lt',
        'COLOR_POST': 'bg-orange-lt',
        'SAMPLE_SPLITTING': 'bg-cyan-lt',
        'INJECTION_MOLDING': 'bg-blue-lt',
        'TESTING': 'bg-yellow-lt',
        'COMPLETED': 'bg-green-lt',
        'CANCELED': 'bg-dark-lt',
    }

    # ---- Status check properties ----
    @property
    def can_start_workflow(self):
        return self.status == 'DRAFT'

    @property
    def is_extrusion_ready(self):
        return self.status in self.EXTRUSION_READY_STATUSES

    @property
    def is_post_extrusion(self):
        return self.status in self.POST_EXTRUSION_STATUSES

    workflow_instance = models.ForeignKey(
        'app_workflow.WorkflowInstance', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="关联审批流程")

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="审批人", related_name='approved_production_orders')
    approved_at = models.DateTimeField("审批通过时间", null=True, blank=True)

    remark = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "生产工单"
        verbose_name_plural = "生产工单"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['creator']),
        ]

    def __str__(self):
        return f"{self.code} [{self.trial_code}]"

    def save(self, *args, **kwargs):
        if not self.code:
            today_str = timezone.now().strftime('%Y%m%d')
            prefix = f"TP{today_str}"
            last = ProductionOrder.objects.filter(
                code__startswith=prefix
            ).order_by('code').last()
            seq = 1
            if last:
                try:
                    seq = int(last.code.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            self.code = f"{prefix}-{seq:02d}"
        super().save(*args, **kwargs)

    @property
    def status_css_class(self):
        return self.STATUS_CSS_MAP.get(self.status, 'bg-secondary-lt')

    @property
    def computed_total_output(self):
        """从样品分拨明细汇总计算总产出"""
        from django.db.models import Sum
        total = self.sample_splits.aggregate(s=Sum('quantity'))['s']
        return total or 0


class ProductionOrderFormulaDetail(models.Model):
    """工单-配方关联明细 — 存储每个配方版本的产量和配色需求"""
    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE,
        related_name='formula_details', verbose_name="关联工单")
    formula = models.ForeignKey(
        'app_formula.LabFormula', on_delete=models.PROTECT,
        verbose_name="配方版本")
    planned_quantity = models.DecimalField("计划产量(kg)", max_digits=10, decimal_places=2, default=0)
    needs_color_matching = models.BooleanField("需要配色", default=False)

    class Meta:
        verbose_name = "工单配方明细"
        verbose_name_plural = "工单配方明细"
        unique_together = ('production_order', 'formula')
        ordering = ['formula__version']
