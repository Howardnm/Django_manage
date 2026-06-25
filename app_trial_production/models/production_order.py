from django.db import models
from django.conf import settings
from django.utils import timezone


class ProductionOrder(models.Model):
    """生产工单 — 试验排产的核心工单"""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '草稿'
        WORKFLOW_RUNNING = 'WORKFLOW_RUNNING', '流程中'
        ACCEPTED = 'ACCEPTED', '已接单'
        EXTRUDING = 'EXTRUDING', '挤出中'
        INJECTION_MOLDING = 'INJECTION_MOLDING', '注塑中'
        TESTING = 'TESTING', '测试中'
        COMPLETED = 'COMPLETED', '已完成'
        CANCELED = 'CANCELED', '已取消'

    # ---- Status groups ----
    HIDDEN_STATUSES = [Status.DRAFT, Status.CANCELED]
    ACTIVE_STATUSES = [Status.WORKFLOW_RUNNING, Status.ACCEPTED, Status.EXTRUDING, Status.INJECTION_MOLDING, Status.TESTING]
    STATUS_FLOW_ORDER = [Status.DRAFT, Status.WORKFLOW_RUNNING, Status.ACCEPTED, Status.EXTRUDING, Status.INJECTION_MOLDING, Status.TESTING, Status.COMPLETED]

    STATUS_CSS_MAP = {
        Status.DRAFT: 'bg-secondary-lt',
        Status.WORKFLOW_RUNNING: 'bg-purple-lt',
        Status.ACCEPTED: 'bg-info-lt',
        Status.EXTRUDING: 'bg-azure-lt',
        Status.INJECTION_MOLDING: 'bg-blue-lt',
        Status.TESTING: 'bg-yellow-lt',
        Status.COMPLETED: 'bg-green-lt',
        Status.CANCELED: 'bg-dark-lt',
    }

    STATUS_DOT_MAP = {
        Status.DRAFT: 'bg-secondary',
        Status.WORKFLOW_RUNNING: 'bg-purple',
        Status.ACCEPTED: 'bg-info',
        Status.EXTRUDING: 'bg-azure',
        Status.INJECTION_MOLDING: 'bg-blue',
        Status.TESTING: 'bg-yellow',
        Status.COMPLETED: 'bg-green',
        Status.CANCELED: 'bg-dark',
    }


    EXTRUSION_DISPLAY_MAP = {
        Status.ACCEPTED: {
            'label': '待挤出', 'badge': 'bg-blue-lt',
            'color': '#e3f2fd', 'border_css': 'border-blue',
            'quantity_badge': 'bg-blue text-white',
        },
        Status.EXTRUDING: {
            'label': '挤出中', 'badge': 'bg-orange-lt',
            'color': '#fff3e0', 'border_css': 'border-orange',
            'quantity_badge': 'bg-orange text-white',
        },
    }

    _EXTRUSION_DONE = {
        'label': '已挤出', 'badge': 'bg-green-lt',
        'color': '#f5f5f5', 'border_css': 'border-green',
        'quantity_badge': 'bg-green text-white',
    }

    # 挤出完成后的状态统一用「已挤出」展示
    for _s in (Status.INJECTION_MOLDING, Status.TESTING, Status.COMPLETED):
        EXTRUSION_DISPLAY_MAP[_s] = _EXTRUSION_DONE

    def _extrusion_display(self, key, default=None):
        """统一获取挤出日历展示属性"""
        if self.status in self.EXTRUSION_DISPLAY_MAP:
            return self.EXTRUSION_DISPLAY_MAP[self.status].get(key, default)
        return default

    # ---- Fields ----
    code = models.CharField("工单号", max_length=50, blank=True, help_text="自动生成，如：TP20250601-01")
    trial_code = models.CharField("实验单号", max_length=50, default='', db_index=True, help_text="对应 LabFormula.code，同批次配方共享")
    project = models.ForeignKey('app_project.Project', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联项目", related_name='production_orders')
    project_node = models.ForeignKey('app_project.ProjectNode', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联项目节点", related_name='production_orders')
    quantity_planned = models.DecimalField("计划产量(kg)", max_digits=10, decimal_places=2, default=25.0)
    quantity_actual = models.DecimalField("实际产量(kg)", max_digits=10, decimal_places=2, null=True, blank=True)
    packaging_desc = models.CharField("包装说明", max_length=100, blank=True)
    storage_location = models.CharField("存放位置", max_length=100, blank=True)
    process_profile = models.ForeignKey('app_process.ProcessProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders', verbose_name="工艺方案")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="创建人", related_name='created_production_orders')
    extruder_operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="挤出操作员", related_name='extruder_orders')
    extrusion_scheduled_date = models.DateTimeField("挤出排产开始时间", null=True, blank=True, help_text="操作员在日历中拖拽排期的开始时间")
    extrusion_scheduled_end = models.DateTimeField("挤出排产结束时间", null=True, blank=True, help_text="计划结束时间，为空则默认开始时间+1小时")
    status = models.CharField("工单状态", max_length=30, choices=Status.choices, default=Status.DRAFT)
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders', verbose_name="关联审批流程")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="审批人", related_name='approved_production_orders')
    approved_at = models.DateTimeField("审批通过时间", null=True, blank=True)
    test_items = models.ManyToManyField('app_material.TestConfig', blank=True, verbose_name="待触发测试项目", related_name="pending_production_orders", help_text="注塑完成后触发创建 TestingTask 时使用")
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
        """工单号 [实验单号]"""
        return f"{self.code} [{self.trial_code}]"

    def save(self, *args, **kwargs):
        """保存时自动生成工单号（如 TP20250623-05）"""
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

    # ---- Status check properties ----
    @property
    def can_start_workflow(self):
        """DRAFT 状态才可发起审批"""
        return self.status == self.Status.DRAFT

    @property
    def can_accept(self):
        """审批流程中才可接单"""
        return self.status == self.Status.WORKFLOW_RUNNING

    @property
    def can_start_extrusion(self):
        """已排产（有挤出计划时间）的已接单工单才能开始挤出"""
        return self.status == self.Status.ACCEPTED and self.extrusion_scheduled_date is not None

    @property
    def is_extrusion_done(self):
        """挤出任务完成且配色任务完成或无需配色"""
        if not hasattr(self, 'extrusion_task'):
            return False
        ext_done = self.extrusion_task.status == 'COMPLETED'
        color_done = (
            not hasattr(self, 'color_task')
            or self.color_task.status in ('COMPLETED', 'NOT_REQUIRED')
        )
        return ext_done and color_done

    @property
    def status_css_class(self):
        """工单状态对应的 Tabler CSS 徽章类"""
        return self.STATUS_CSS_MAP.get(self.status, 'bg-secondary-lt')

    @property
    def status_dot_color(self):
        """工单状态对应的状态点颜色类"""
        return self.STATUS_DOT_MAP.get(self.status, 'bg-secondary')

    @property
    def status_label(self):
        """工单状态中文显示"""
        return self.Status(self.status).label

    # ---- Extrusion calendar display properties ----
    @property
    def extrusion_status_label(self):
        return self._extrusion_display('label', '')

    @property
    def extrusion_status_badge(self):
        return self._extrusion_display('badge', '')

    @property
    def is_extrusion_readonly(self):
        """挤出日历中是否只读（已接单后才可拖拽排期）"""
        return self.status != self.Status.ACCEPTED

    @property
    def extrusion_calendar_color(self):
        return self._extrusion_display('color', '#e3f2fd')

    @property
    def extrusion_calendar_border(self):
        return self._extrusion_display('border_css', 'border-blue')

    @property
    def extrusion_quantity_badge(self):
        return self._extrusion_display('quantity_badge', 'bg-blue text-white')


class ProductionOrderFormulaDetail(models.Model):
    """工单-配方关联明细 — 存储每个配方版本的产量和配色需求"""
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='formula_details', verbose_name="关联工单")
    formula = models.ForeignKey('app_formula.LabFormula', on_delete=models.PROTECT, verbose_name="配方版本")
    planned_quantity = models.DecimalField("计划产量(kg)", max_digits=10, decimal_places=2, default=0)
    needs_color_matching = models.BooleanField("需要配色", default=False)

    class Meta:
        verbose_name = "工单配方明细"
        verbose_name_plural = "工单配方明细"
        constraints = [
            models.UniqueConstraint(
                fields=['production_order', 'formula'],
                name='unique_formula_per_production_order',
            ),
        ]
        ordering = ['formula__version']
