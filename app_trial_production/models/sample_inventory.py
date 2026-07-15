from django.db import models


class SampleInventory(models.Model):
    """
    统一样品库存 — 通过 type + sub_type 区分颗粒样品和样条样品，status 跟踪生命周期。

    流转模型：
        PELLET + FINISHED       : IN_LAB ──→ SAP_STORED   (SAP入库)
        PELLET + FOR_INJECTION  : IN_LAB ──→ CONSUMED     (注塑消耗)
        SPECIMEN + FOR_TESTING  : IN_LAB ──→ CONSUMED     (测试完成消耗)

    颗粒样品 (PELLET)：
      - FINISHED: 颗粒成品，已满足交付标准，可入SAP仓库
      - FOR_INJECTION: 待打样颗粒，供注塑取样使用

    样条样品 (SPECIMEN)：
      - FOR_TESTING: 待测试样条，注塑产出后入样品库
      - TESTED: 已测试样条（保留选项，实际流转由 status=CONSUMED 驱动）
    """

    class Type(models.TextChoices):
        PELLET = 'PELLET', '颗粒样品'
        SPECIMEN = 'SPECIMEN', '样条样品'

    class SubType(models.TextChoices):
        FINISHED = 'FINISHED', '颗粒成品'
        FOR_INJECTION = 'FOR_INJECTION', '待打样颗粒'
        FOR_TESTING = 'FOR_TESTING', '待测试样条'
        TESTED = 'TESTED', '已测试样条'

    class Status(models.TextChoices):
        IN_LAB = 'IN_LAB', '在实验房'
        SAP_STORED = 'SAP_STORED', '已入SAP仓库'
        CONSUMED = 'CONSUMED', '已消耗'

    # ---- 类型区分 ----
    type = models.CharField("样品类型", max_length=20, choices=Type.choices, db_index=True, default='PELLET')
    sub_type = models.CharField("子类型", max_length=30, choices=SubType.choices, db_index=True, default='FINISHED')
    status = models.CharField("库存状态", max_length=20, choices=Status.choices, default=Status.IN_LAB)

    # ---- 通用关联 ----
    production_order = models.ForeignKey('app_trial_production.ProductionOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='sample_inventories', verbose_name="关联工单")
    formula = models.ForeignKey('app_formula.LabFormula', on_delete=models.SET_NULL, null=True, blank=True, related_name='sample_inventories', verbose_name="对应配方版本")
    trial_code = models.CharField("实验单号", max_length=50, default='', db_index=True, help_text="按实验单号分组展示")
    batch_number = models.CharField("批次号", max_length=100, default='', db_index=True, help_text="同一工单+同一配方版本 = 同一批，格式: 工单号-V配方版本")

    # ---- 数量 ----
    quantity = models.DecimalField("数量(kg)", max_digits=10, decimal_places=2, null=True, blank=True, help_text="颗粒样品用")
    specimen_count = models.PositiveIntegerField("样条数量", null=True, blank=True, help_text="样条样品用")
    specimen_qualified = models.PositiveIntegerField("合格数量", null=True, blank=True, help_text="可送测试中心的数量")

    # ---- 存放信息 ----
    storage_location = models.CharField("存放位置", max_length=100, blank=True)
    packaging_desc = models.CharField("包装说明", max_length=100, blank=True)

    # ---- SAP 入库信息（替代客户寄出） ----
    sap_material_code = models.CharField("SAP物料号", max_length=50, blank=True)
    sap_batch_number = models.CharField("SAP批次号", max_length=50, blank=True)
    sap_warehouse_date = models.DateField("SAP入库日期", null=True, blank=True)
    sap_storage_location = models.CharField("SAP库位", max_length=50, blank=True)

    # ---- 注塑关联（样条来源） ----
    injection_task = models.ForeignKey('app_mold_injection.InjectionTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='output_specimens', verbose_name="来源注塑任务", help_text="样条样品的来源注塑任务")
    mold = models.ForeignKey('app_mold_injection.MoldType', on_delete=models.SET_NULL, null=True, blank=True, related_name='sample_inventories_by_mold', verbose_name="对应模具", help_text="样条样品对应的模具")
    batch_label = models.CharField("批次标签", max_length=50, blank=True)
    is_competitor_sample = models.BooleanField("竞品样品", default=False)

    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "样品库存"
        verbose_name_plural = "样品库存"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trial_code']),
            models.Index(fields=['type', 'sub_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        type_label = self.get_type_display()
        sub_label = self.get_sub_type_display()
        if self.type == self.Type.PELLET:
            return f"[{self.trial_code}] {type_label}-{sub_label} {self.quantity or 0}kg"
        return f"[{self.trial_code}] {type_label}-{sub_label} ×{self.specimen_count or 0}"

    @property
    def status_css_class(self):
        return {
            self.Status.IN_LAB: 'bg-azure-lt',
            self.Status.SAP_STORED: 'bg-green-lt',
            self.Status.CONSUMED: 'bg-secondary-lt',
        }.get(self.status, 'bg-secondary-lt')

    @property
    def is_pellet(self):
        return self.type == self.Type.PELLET

    @property
    def is_specimen(self):
        return self.type == self.Type.SPECIMEN

    @property
    def can_sap_entry(self):
        """是否可执行SAP入库 — 仅成品颗粒允许入SAP仓库。

        待打样颗粒 (FOR_INJECTION) 会被注塑消耗，
        样条样品 (SPECIMEN) 会被测试消耗，均不允许入SAP。
        """
        return (
            self.type == self.Type.PELLET
            and self.sub_type == self.SubType.FINISHED
            and self.status == self.Status.IN_LAB
        )

    @property
    def is_reserved_for_injection(self):
        """FOR_INJECTION 颗粒是否已关联工单注塑任务（渠道A）。

        关联后不允许创建独立注塑任务（渠道B），
        应由工单注塑任务自动消耗。
        """
        return (
            self.type == self.Type.PELLET
            and self.sub_type == self.SubType.FOR_INJECTION
            and self.injection_task is not None
        )
