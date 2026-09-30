"""产品报价需求单表单层。

发起表单为「FK 字段 + 动态字段」混排：FK 字段（产品/客户/业务组别/所属公司/业务员）
固定声明，其余填写项由 QuotationField（admin 维护）动态生成。

选择框策略（tomselect 规范）：
- finished_material / customer —— 远程搜索（大数据量外键）
- salesperson —— 通用人员选择器 UserPickerWidget（组织树弹窗选人）
- business_group / subsidiary / 动态枚举 —— 本地 TomSelect（小表）
"""

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse

from app_material.models import MaterialLibrary
from app_repository.models import Customer
from app_user.models import Subsidiary, User, WorkGroup
from common_utils.filters import TablerFormMixin
from common_utils.forms import UserPickerWidget

from .models import QuotationField


class QuotationCreateForm(TablerFormMixin, forms.Form):
    """步骤① 基本信息表单（发起报价）。"""

    finished_material = forms.ModelChoiceField(
        label="SAP编码", queryset=MaterialLibrary.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-select remote-search',
            'data-model': 'material_sap',
            'placeholder': '搜索SAP编码…',
        }))
    product_name = forms.CharField(
        label="产品名称", required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}))
    product_type = forms.CharField(
        label="产品类型", required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}))
    customer = forms.ModelChoiceField(
        label="客户名称", queryset=Customer.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-select remote-search',
            'data-model': 'customer',
            'placeholder': '搜索客户名称…',
        }))
    business_group = forms.ModelChoiceField(
        label="业务组别", queryset=WorkGroup.objects.all(),
        widget=forms.Select(attrs={'placeholder': '请选择业务组别'}))
    subsidiary = forms.ModelChoiceField(
        label="所属公司（分基地）", queryset=Subsidiary.objects.all(),
        widget=forms.Select(attrs={'placeholder': '请选择所属公司'}))
    salesperson = forms.CharField(
        label="业务员", widget=UserPickerWidget(multi=False, title='选择业务员'), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 动态字段：遍历 admin 维护的 QuotationField
        for field in (QuotationField.objects.filter(is_active=True)
                      .order_by('order', 'id').prefetch_related('options')):
            self.fields[field.key] = self._build_field(field)
        self._compress_remote_querysets()
        self._set_remote_api_urls()

    def _compress_remote_querysets(self):
        """远程搜索字段：GET 渲染时压缩 queryset，避免本地渲染全量选项。

        POST 校验失败时只保留已提交的那条，使其以 <option selected> 回显，
        其余选项由 TomSelect 远程搜索按需拉取（memory forms.md §3.1）。
        """
        base = {
            'finished_material': MaterialLibrary.objects.all(),
            'customer': Customer.objects.all(),
        }
        for name, qs in base.items():
            f = self.fields[name]
            pk = None
            if self.data:
                pk = self.data.get(name)
            elif name in self.initial:
                pk = self.initial.get(name)  # 编辑态回显已选值
            f.queryset = qs.filter(pk=pk) if pk else qs.none()

    def _set_remote_api_urls(self):
        """远程搜索 API 地址写在元素 data-api-url，JS 不硬编码 URL。"""
        self.fields['finished_material'].widget.attrs['data-api-url'] = reverse('common_autocomplete')
        self.fields['customer'].widget.attrs['data-api-url'] = reverse('repo_api_search')

    def clean_salesperson(self):
        """UserPickerWidget 返回用户 ID 字符串，转成 User 实例。"""
        user_id = self.cleaned_data.get('salesperson')
        if not user_id:
            return None
        try:
            return User.objects.get(pk=int(user_id), is_active=True)
        except (ValueError, TypeError, User.DoesNotExist):
            raise ValidationError('所选用户不存在或已禁用')

    def _build_field(self, field):
        """按字段类型构造动态表单字段，label/required 取自字段定义。

        注意：动态字段在 TablerFormMixin.__init__ 之后才加入，Mixin 的
        CSS 类注入不会作用到它们，故此处手动补全统一的 Tabler class。
        """
        if field.field_type == QuotationField.FieldType.SELECT:
            choices = [('', '——')] + [
                (o.code, o.label) for o in field.options.all() if o.is_active
            ]
            return forms.ChoiceField(
                label=field.label, required=field.required,
                choices=choices, initial=field.default_value or None,
                widget=forms.Select(attrs={
                    'class': 'form-select form-select-search',
                    'placeholder': f'请选择{field.label}',
                }),
            )
        if field.field_type == QuotationField.FieldType.NUMBER:
            return forms.DecimalField(
                label=field.label, required=field.required,
                initial=field.default_value or None,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control', 'step': '0.01',
                    'placeholder': f'请输入{field.label}',
                }),
            )
        if field.field_type == QuotationField.FieldType.DATE:
            # 日期不预填默认值（避免字符串解析失败），由用户选择
            return forms.DateField(
                label=field.label, required=field.required,
                widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            )
        return forms.CharField(
            label=field.label, required=field.required,
            initial=field.default_value or None,
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': f'请输入{field.label}',
            }),
        )
