"""
产品报价需求单模块数据层。

Models:
    QuotationField         — 报价字段定义（admin 维护，基本信息卡片动态填写项，只增不减）
    ChoiceOption           — 字段选项表（下拉/布尔选项）
    QuotationRequest       — 产品报价需求单主表（14 步审批流）
    QuotationBOM           — 候选配方（步骤②多选，步骤⑤选定）
    QuotationMaterialPrice — 原材料行情价明细（步骤③采购填写）
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class QuotationField(models.Model):
    """报价字段定义 — 基本信息卡片的填写项由 admin 动态维护，只增不减。

    除 FK 字段（成品/客户/业务组别/分基地/销售员）外，基本信息的所有填写项
    （下拉/布尔/文本/数字/日期）都由此表定义，表单据此动态生成控件。
    """

    class FieldType(models.TextChoices):
        SELECT = 'select', '下拉选择'
        TEXT = 'text', '单行文本'
        NUMBER = 'number', '数字'
        DATE = 'date', '日期'

    key = models.CharField("字段键", max_length=50, unique=True,
                           help_text="存储键，创建后请勿修改（历史快照依赖它）")
    label = models.CharField("字段名", max_length=100)
    field_type = models.CharField("控件类型", max_length=20,
                                  choices=FieldType.choices, default=FieldType.SELECT)
    hint = models.CharField("字段解释", max_length=200, blank=True,
                            help_text="表单中显示为红色解释文字")
    group = models.CharField("分组", max_length=50, blank=True, default='',
                             help_text="发起表单中的分区标题，如「台板与包装」")
    order = models.PositiveIntegerField("排序", default=0)
    required = models.BooleanField("必填", default=False)
    default_value = models.CharField("默认值", max_length=100, blank=True,
                                     help_text="选项编码或文本，留空则不预填（布尔填 NO 默认选「否」）")
    is_active = models.BooleanField("启用", default=True,
                                    help_text="停用后新表单不再显示，但历史需求单数据仍保留")
    description = models.TextField("说明", blank=True)

    class Meta:
        verbose_name = "报价字段定义"
        verbose_name_plural = "报价字段定义"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.label} ({self.key})"


class ChoiceOption(models.Model):
    """字段选项表 — 属于某个 QuotationField 的下拉/布尔选项。"""

    field = models.ForeignKey(
        QuotationField, on_delete=models.CASCADE, related_name='options', verbose_name="所属字段")
    code = models.CharField("选项编码", max_length=50)
    label = models.CharField("选项名称", max_length=100)
    order = models.PositiveIntegerField("排序权重", default=0)
    is_active = models.BooleanField("是否启用", default=True)
    description = models.TextField("描述", blank=True)

    class Meta:
        verbose_name = "枚举选项"
        verbose_name_plural = "枚举选项"
        ordering = ['field__order', 'order', 'code']
        unique_together = ('field', 'code')

    def __str__(self):
        return f"{self.field.label}: {self.label}"

    @classmethod
    def get_choices(cls, field_key):
        """返回指定字段 key 的 [(code, label)]。"""
        return list(
            cls.objects.filter(field__key=field_key, field__is_active=True, is_active=True)
            .order_by('order', 'code')
            .values_list('code', 'label')
        )

    @classmethod
    def get_label(cls, field_key, code):
        """按字段 key + 编码取显示名，查不到返回 code 本身。"""
        if not code:
            return ''
        return dict(cls.get_choices(field_key)).get(code, code)


class QuotationRequest(models.Model):
    """产品报价需求单主表。"""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '草稿'
        RUNNING = 'RUNNING', '审批中'
        COMPLETED = 'COMPLETED', '已完成'
        REJECTED = 'REJECTED', '已驳回'
        CANCELED = 'CANCELED', '已取消'

    code = models.CharField("需求单号", max_length=50, unique=True, blank=True)

    # 路由字段（FK，固定列）
    finished_material = models.ForeignKey(
        'app_material.MaterialLibrary', on_delete=models.PROTECT, verbose_name="成品材料")
    customer = models.ForeignKey(
        'app_repository.Customer', on_delete=models.PROTECT, verbose_name="关联客户")
    business_group = models.ForeignKey(
        'app_user.WorkGroup', on_delete=models.PROTECT, verbose_name="业务组别")
    subsidiary = models.ForeignKey(
        'app_user.Subsidiary', on_delete=models.PROTECT, verbose_name="分基地")

    # 人员字段
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='created_quotations', verbose_name="发起人")
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sales_quotations', verbose_name="销售员")

    # 基本信息动态字段快照：{field_key: str_value}，字段定义见 QuotationField
    form_data = models.JSONField("表单数据", default=dict, blank=True)

    # 后置流程字段（非基本信息，保持固定列）
    marginal_cost = models.DecimalField("边际成本", max_digits=12, decimal_places=2, null=True, blank=True)
    contribution_rate = models.DecimalField("边际贡献率", max_digits=6, decimal_places=4, null=True, blank=True)
    customer_price = models.DecimalField("客户含税报价", max_digits=12, decimal_places=2, null=True, blank=True)

    # 流程字段
    workflow_instance = models.OneToOneField(
        'app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quotation_request', verbose_name="审批流程实例")
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.DRAFT)

    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "产品报价需求单"
        verbose_name_plural = "产品报价需求单"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_code(cls):
        """生成需求单号，形如 Q20260924-001。"""
        prefix = f"Q{timezone.now():%Y%m%d}"
        last = (
            cls.objects.filter(code__startswith=prefix)
            .order_by('-code')
            .values_list('code', flat=True)
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f"{prefix}-{seq:03d}"

    @property
    def current_task(self):
        """当前待处理任务（PENDING），卡片据此门控。"""
        if not self.workflow_instance_id:
            return None
        return self.workflow_instance.tasks.filter(status='PENDING').first()

    @property
    def needs_revision(self):
        """是否处于「退回发起者修订」状态（_need_revision 标记，无 PENDING 任务）。"""
        instance = self.workflow_instance
        return bool(instance and (instance.context_data or {}).get('_need_revision'))

    @property
    def status_badge_class(self):
        return {
            self.Status.DRAFT: 'bg-secondary-lt',
            self.Status.RUNNING: 'bg-azure-lt',
            self.Status.COMPLETED: 'bg-green-lt',
            self.Status.REJECTED: 'bg-red-lt',
            self.Status.CANCELED: 'bg-secondary-lt',
        }.get(self.status, 'bg-secondary-lt')

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('quotation_detail', kwargs={'pk': self.pk})

    def get_field_value(self, key):
        """取动态字段的原始值（快照）。"""
        return self.form_data.get(key)

    def get_field_display(self, key):
        """取动态字段的展示值：select 取选项 label，其余原样。"""
        value = self.form_data.get(key)
        if value in (None, ''):
            return ''
        field = QuotationField.objects.filter(key=key).first()
        if field is not None and field.field_type == QuotationField.FieldType.SELECT:
            return ChoiceOption.get_label(key, value)
        return value

    def get_dynamic_fields(self):
        """返回动态字段展示列表 [{field, value, display}]（批量查询，避免 N+1）。

        启用字段全部返回；已停用字段仅在历史快照有值时返回，
        这样 admin 停用字段不会让历史需求单的数据凭空消失。
        """
        fields = list(QuotationField.objects.all()
                      .order_by('order', 'id').prefetch_related('options'))
        rows = []
        for f in fields:
            value = self.form_data.get(f.key)
            if not f.is_active and value in (None, ''):
                continue
            display = value or ''
            if f.field_type == QuotationField.FieldType.SELECT and value:
                display = next(
                    (o.label for o in f.options.all() if o.code == value), value)
            rows.append({'field': f, 'value': value, 'display': display})
        return rows

    def get_info_sections(self):
        """信息卡片只读展示数据：分区 + 每行 4 字段，供 detail/print 表格渲染。

        返回 [{'name': str, 'rows': [[cell|None, … 4 个], …]}, …]，
        cell = {'label': str, 'display': str}。meta（申请单号/申请人/…/所属公司）
        归入「基本信息」分区，动态字段按 QuotationField.group 归入各自分区。
        """
        meta = [
            ('申请单号', self.code),
            ('申请人', self.creator.username),
            ('申请日期', timezone.localtime(self.created_at).strftime('%Y-%m-%d')),
            ('业务员', self.salesperson.username if self.salesperson else ''),
            ('产品名称', self.finished_material.grade_name),
            ('SAP编码', self.finished_material.sap_material_code),
            ('产品类型', self.finished_material.category.name if self.finished_material.category_id else ''),
            ('客户名称', self.customer.short_name or self.customer.company_name),
            ('业务组别', self.business_group.name),
            ('所属公司', self.subsidiary.name),
        ]

        sections, index = [], {}
        def get_section(name):
            if name not in index:
                index[name] = {'name': name, 'cells': []}
                sections.append(index[name])
            return index[name]

        get_section('基本信息')['cells'].extend(
            {'label': label, 'display': display} for label, display in meta)
        for d in self.get_dynamic_fields():
            get_section(d['field'].group or '其他')['cells'].append(
                {'label': d['field'].label, 'display': d['display']})

        result = []
        for s in sections:
            cells = s['cells']
            rows = []
            for i in range(0, len(cells), 4):
                row = cells[i:i + 4]
                row += [None] * (4 - len(row))
                rows.append(row)
            result.append({'name': s['name'], 'rows': rows})
        return result


class QuotationBOM(models.Model):
    """需求单候选配方（步骤②多选），步骤⑤选定其中一个。"""

    request = models.ForeignKey(
        QuotationRequest, on_delete=models.CASCADE, related_name='boms', verbose_name="需求单")
    formula = models.ForeignKey(
        'app_formula.LabFormula', on_delete=models.PROTECT, verbose_name="配方")
    is_selected = models.BooleanField("最终选定", default=False)
    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选定人")

    class Meta:
        verbose_name = "候选配方"
        verbose_name_plural = "候选配方"
        unique_together = ('request', 'formula')

    def __str__(self):
        return f"{self.request.code} - {self.formula.name}"


class QuotationMaterialPrice(models.Model):
    """原材料行情价明细（步骤③采购填写），按 (request, raw_material) 唯一。"""

    request = models.ForeignKey(
        QuotationRequest, on_delete=models.CASCADE, related_name='material_prices', verbose_name="需求单")
    raw_material = models.ForeignKey(
        'app_raw_material.RawMaterial', on_delete=models.PROTECT, verbose_name="原材料")
    price_tax_included = models.DecimalField("含税行情价", max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField("税率", max_digits=5, decimal_places=4, default=Decimal('0.13'))
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="录入人")
    entered_at = models.DateTimeField("录入时间", auto_now_add=True)

    class Meta:
        verbose_name = "原材料行情价明细"
        verbose_name_plural = "原材料行情价明细"
        unique_together = ('request', 'raw_material')

    def __str__(self):
        return f"{self.request.code} - {self.raw_material.name} ¥{self.price_tax_included}"

    @property
    def price_tax_excluded(self):
        """不含税价 = 含税 / (1 + 税率)。"""
        return self.price_tax_included / (1 + self.tax_rate)
