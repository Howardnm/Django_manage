from django import forms
from .models import Customer, ProjectRepository, ProjectFile, OEM, Salesperson, OEMStandardFile
from app_material.models import MaterialLibrary
from common_utils.filters import TablerFormMixin # 从 common_utils 导入通用的 TablerFormMixin
from app_project.models import ProjectNode

# ==============================================================================
# 1. 客户表单
# ==============================================================================
class CustomerForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'


# ==============================================================================
# 3. 项目档案表单 (主表)
# ==============================================================================

class ProjectRepositoryForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectRepository
        exclude = ['project', 'updated_at']
        # Widget 这里加上特殊的 class，比如 'remote-search'，方便 JS 识别
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer'}),
            'oem': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'oem'}),
            'material': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'material'}),
            'salesperson': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'salesperson'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 【性能核心优化】
        # 如果没有 data (说明是 GET 请求渲染页面)，则清空 QuerySet，避免渲染成千上万个 option
        # 但是，必须保留 "当前已选" 的那个值，否则页面上显示为空
        if not self.data:
            instance = kwargs.get('instance')
            if instance and instance.material_id: self.fields['material'].queryset = MaterialLibrary.objects.filter(pk=instance.material_id)
            else: self.fields['material'].queryset = MaterialLibrary.objects.none()
            if instance and instance.customer_id: self.fields['customer'].queryset = Customer.objects.filter(pk=instance.customer_id)
            else: self.fields['customer'].queryset = Customer.objects.none()
            if instance and instance.oem_id: self.fields['oem'].queryset = OEM.objects.filter(pk=instance.oem_id)
            else: self.fields['oem'].queryset = OEM.objects.none()
            if instance and instance.salesperson_id: self.fields['salesperson'].queryset = Salesperson.objects.filter(pk=instance.salesperson_id)
            else: self.fields['salesperson'].queryset = Salesperson.objects.none()
        self.fields['oem'].label_from_instance = lambda obj: f"{obj.name} ({obj.short_name})" if obj.short_name else obj.name

        # 注意：如果是 POST 请求 (self.data存在)，不要动 queryset
        # Django 需要用完整的 .all() (或者包含提交值的 queryset) 来验证数据有效性
        # 但因为 ModelChoiceField 默认就是 .all()，所以不需要额外写代码


# 4. 【新增】项目文件上传表单 (适配新字段)
class ProjectFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectFile
        fields = ['node', 'file_type', 'file', 'version', 'description']
        widgets = {
            'node': forms.Select(attrs={'class': 'form-select'}),
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '数字，如: 1'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': '版本变更说明...'}),
        }

    def __init__(self, *args, **kwargs):
        repository = kwargs.pop('repository', None)
        super().__init__(*args, **kwargs)
        if repository:
            # 限制 node 只能选当前项目的
            self.fields['node'].queryset = ProjectNode.objects.filter(project=repository.project).order_by('order')
            # 自定义下拉框显示文本：节点阶段名称 + 轮次
            self.fields['node'].label_from_instance = lambda obj: f"{obj.get_stage_display()} (第{obj.round}轮)"
            self.fields['node'].empty_label = "--- 不关联具体节点 (通用资料) ---"


# 【新增】业务员管理表单
class SalespersonForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Salesperson
        fields = ['name', 'phone', 'email']


# ==============================================================================
# 6. 主机厂表单
# ==============================================================================
class OEMForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEM
        fields = ['name', 'short_name', 'website', 'cooperation_level', 'contact_name', 'contact_phone', 'contact_email', 'address', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '备注信息...'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': '公司详细地址...'}),
            'cooperation_level': forms.Select(attrs={'class': 'form-select'}),
        }

# 主机厂标准文件表单 (适配新字段)
class OEMStandardFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEMStandardFile
        fields = ['file_type', 'file', 'version', 'description']
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': '版本变更说明...'}),
        }
