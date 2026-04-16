from django import forms
from django.contrib.auth.models import User
from .models import Customer, ProjectRepository, ProjectFile, OEM, OEMStandardFile
from app_material.models.material import MaterialLibrary
from common_utils.filters import TablerFormMixin
from app_project.models import ProjectNode

# ==============================================================================
# 1. 客户表单
# ==============================================================================
class CustomerForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['company_name', 'short_name', 'address', 'contact_name', 'phone', 'email', 'is_active']


# ==============================================================================
# 3. 项目档案表单
# ==============================================================================
class ProjectRepositoryForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectRepository
        exclude = ['project', 'updated_at']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer'}),
            'oem': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'oem'}),
            'material': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'material'}),
            # 业务员现在搜索 User
            'salesperson': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'salesperson'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.data:
            instance = kwargs.get('instance')
            # 材质处理
            if instance and instance.material_id:
                self.fields['material'].queryset = MaterialLibrary.objects.filter(pk=instance.material_id)
            else:
                self.fields['material'].queryset = MaterialLibrary.objects.none()
            
            # 客户处理
            if instance and instance.customer_id:
                self.fields['customer'].queryset = Customer.objects.filter(pk=instance.customer_id)
            else:
                self.fields['customer'].queryset = Customer.objects.none()
            
            # OEM处理
            if instance and instance.oem_id:
                self.fields['oem'].queryset = OEM.objects.filter(pk=instance.oem_id)
            else:
                self.fields['oem'].queryset = OEM.objects.none()
            
            # 【重要】业务员处理 (User 模型)
            if instance and instance.salesperson_id:
                self.fields['salesperson'].queryset = User.objects.filter(pk=instance.salesperson_id)
            else:
                self.fields['salesperson'].queryset = User.objects.none()

        self.fields['oem'].label_from_instance = lambda obj: f"{obj.name} ({obj.short_name})" if obj.short_name else obj.name
        # 业务员显示全名
        self.fields['salesperson'].label_from_instance = lambda obj: obj.get_full_name() or obj.username


# 4. 项目文件上传表单
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
            self.fields['node'].empty_label = "--- 不关联具体节点 (通用资料) ---"


# ==============================================================================
# 6. 主机厂表单
# ==============================================================================
class OEMForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEM
        fields = ['name', 'short_name', 'website', 'contact_name', 'contact_phone', 'contact_email', 'address', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'address': forms.Textarea(attrs={'rows': 2}),
        }

class OEMStandardFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEMStandardFile
        fields = ['file_type', 'file', 'version', 'description']
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }
