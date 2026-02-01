from django import forms
from common_utils.filters import TablerFormMixin
from .models import MachineModel, ScrewCombination, ProcessProfile


# 1. 机台型号表单
class MachineModelForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MachineModel
        fields = '__all__'
        widgets = {
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# 2. 螺杆组合表单
class ScrewCombinationForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ScrewCombination
        fields = '__all__'
        widgets = {
            'machines': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# 3. 工艺方案表单
class ProcessProfileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProcessProfile
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'qc_check_points': forms.Textarea(attrs={'rows': 3}),
            # 移除 no-tomselect，添加 tomselect-multi-local，让 TomSelect 以多选模式初始化
            'material_types': forms.SelectMultiple(attrs={'class': 'form-select tomselect-multi-local'}), 
            # 添加 remote-search 和 data-model 属性
            'machine': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'machinemodel'}),
            'screw_combination': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'screwcombination'}),
            'cooling_method': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 【性能核心优化】
        # 如果没有 data (说明是 GET 请求渲染页面)，则清空 QuerySet，避免渲染成千上万个 option
        # 但是，必须保留 "当前已选" 的那个值，否则页面上显示为空
        if not self.data:
            instance = kwargs.get('instance')

            # 1. 优化机台字段
            if instance and instance.machine_id:
                self.fields['machine'].queryset = MachineModel.objects.filter(pk=instance.machine_id)
            else:
                self.fields['machine'].queryset = MachineModel.objects.none()

            # 2. 优化螺杆组合字段
            if instance and instance.screw_combination_id:
                self.fields['screw_combination'].queryset = ScrewCombination.objects.filter(pk=instance.screw_combination_id)
            else:
                self.fields['screw_combination'].queryset = ScrewCombination.objects.none()

        # 注意：如果是 POST 请求 (self.data 存在)，不要动 queryset
        # Django 需要用完整的 .all() (或者包含提交值的 queryset) 来验证数据有效性
        # 但因为 ModelChoiceField 默认就是 .all()，所以不需要额外写代码
