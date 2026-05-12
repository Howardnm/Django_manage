from django import forms
from django.contrib.auth import get_user_model
from .models import Customer, ProjectRepository, ProjectFile, OEM, OEMStandardFile, GradeFactor
from common_utils.filters import TablerFormMixin
from app_project.models import ProjectNode

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
        # 核心修正：移除模型中不存在的 is_active 字段
        fields = ['company_name', 'short_name', 'logo', 'address', 'business_license_code', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '请输入客户公司简介...'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': '公司注册或办公地址'}),
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
    class Meta:
        model = ProjectRepository
        exclude = ['project', 'updated_at']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer'}),
            'oem': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'oem'}),
            'salesperson': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'salesperson'}),
        }

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
            
            if instance and instance.salesperson_id:
                self.fields['salesperson'].queryset = User.objects.filter(pk=instance.salesperson_id)
            else:
                self.fields['salesperson'].queryset = User.objects.none()

        self.fields['oem'].label_from_instance = lambda obj: f"{obj.name} ({obj.short_name})" if obj.short_name else obj.name
        self.fields['salesperson'].label_from_instance = lambda obj: obj.get_full_name() or obj.username


# ==========================================
# 4. 项目文件上传表单
# ==========================================
class ProjectFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectFile
        fields = ['node', 'file_type', 'file', 'version', 'description']
        widgets = {
            'node': forms.Select(attrs={'class': 'form-select'}),
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        repository = kwargs.pop('repository', None)
        super().__init__(*args, **kwargs)
        if repository:
            self.fields['node'].queryset = ProjectNode.objects.filter(project=repository.project).order_by('order')
            self.fields['node'].label_from_instance = lambda obj: f"{obj.get_stage_display()} (第{obj.round}轮)"
            self.fields['node'].empty_label = "--- 通用资料 (不关联节点) ---"


# ==========================================
# 5. 主机厂标准文件表单
# ==========================================
class OEMStandardFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEMStandardFile
        fields = ['file_type', 'file', 'version', 'description']
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }
