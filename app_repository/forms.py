from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import Customer, ProjectRepository, OEM, GradeFactor
from common_utils.filters import TablerFormMixin
from common_utils.forms import UserPickerWidget

User = get_user_model()

# ==========================================
# 0. 等级因子表单
# ==========================================
class GradeFactorForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = GradeFactor
        fields = ['name', 'factor', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '请输入等级说明...'}),
        }

# ==========================================
# 1. 客户公司表单 (公司实体级)
# ==========================================
class CustomerForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'customer_code', 'company_name', 'company_name_2', 'short_name', 'search_term_2',
            'account_group', 'account_group_name', 'customer_series', 'industry',
            'trade_partner', 'vendor_code', 'address_number', 'business_license_code',
            'country_code', 'country_name', 'region_code', 'region_name', 'city',
            'street', 'house_number', 'postal_code', 'address',
            'phone', 'phone_2', 'email', 'customer_source',
            'sales_region', 'sales_manager_name', 'sales_person_name',
            'posting_blocked', 'sales_area_blocked', 'group_deleted',
            'sales_order_block', 'delivery_block', 'billing_block',
            'sap_created_by', 'sap_created_on',
            'logo', 'description',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '请输入客户公司简介...'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': '公司注册或办公地址'}),
            'sap_created_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'posting_blocked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sales_area_blocked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'group_deleted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ==========================================
# 2. 主机厂公司表单 (公司实体级)
# ==========================================
class OEMForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEM
        fields = ['name', 'short_name', 'logo', 'website', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '请输入主机厂品牌简介...'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://...'}),
        }


# ==========================================
# 3. 项目商务档案表单
# ==========================================
class ProjectRepositoryForm(TablerFormMixin, forms.ModelForm):
    submission_comment = forms.CharField(
        label="提交意见",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': '请说明本次编辑档案的原因（如：客户压价、新材料替换、用量变更等）',
        }),
        required=True,
        help_text="编辑档案信息需填写变更原因并提交审批，审批通过后生效"
    )

    salesperson = forms.CharField(
        widget=UserPickerWidget(multi=False, title='选择业务员'),
        required=False,
    )

    class Meta:
        model = ProjectRepository
        exclude = ['project', 'updated_at', 'workflow_instance']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer'}),
            'oem': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'oem'}),
            'first_sample_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'first_trial_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'first_trial_cycle_days': forms.NumberInput(attrs={'placeholder': '如：30'}),
            'pilot_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'mass_production_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def clean_salesperson(self):
        """将 UserPickerWidget 返回的用户 ID 字符串转为 User 实例"""
        user_id = self.cleaned_data.get('salesperson')
        if not user_id:
            return None
        try:
            return User.objects.get(pk=int(user_id), is_active=True)
        except (ValueError, TypeError, User.DoesNotExist):
            raise ValidationError('所选用户不存在或已禁用')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data:
            instance = kwargs.get('instance')
            if instance and instance.customer_id:
                self.fields['customer'].queryset = Customer.objects.filter(pk=instance.customer_id)
            else:
                self.fields['customer'].queryset = Customer.objects.none()

            if instance and instance.oem_id:
                self.fields['oem'].queryset = OEM.objects.filter(pk=instance.oem_id)
            else:
                self.fields['oem'].queryset = OEM.objects.none()

        self.fields['oem'].label_from_instance = lambda obj: f"{obj.name} ({obj.short_name})" if obj.short_name else obj.name

        # 项目计划时间节点：已录入的字段禁用编辑，仅允许首次录入
        plan_fields = ['first_sample_date', 'first_trial_date', 'first_trial_cycle_days',
                       'pilot_date', 'mass_production_date']
        instance = kwargs.get('instance')
        if instance and instance.pk:
            for f in plan_fields:
                if getattr(instance, f) is not None:
                    self.fields[f].widget.attrs['disabled'] = True
                    self.fields[f].required = False
