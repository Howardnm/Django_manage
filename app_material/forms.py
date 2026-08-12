from django import forms
from django.forms import inlineformset_factory

from .models.material import (MaterialLibrary, ApplicationScenario, MaterialDataPoint,
                               TestConfig, MaterialType, MaterialCharacteristic)
from common_utils.filters import TablerFormMixin


class MaterialForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialLibrary
        fields = '__all__'
        exclude = ['creator']  # 创建人由视图程序化赋值，不渲染到表单
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            # 应用场景多选
            'scenarios': forms.SelectMultiple(attrs={
                'class': 'form-select remote-search tomselect-multi-remote', 
                'data-model': 'scenario'
            }),
            # 特征属性多选
            'characteristics': forms.SelectMultiple(attrs={
                'class': 'form-select remote-search tomselect-multi-remote', 
                'data-model': 'characteristic' 
            }),
            'flammability': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'sap_material_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SAP物料编码，如：A01000212345'}),
            # 对外发布开关 (使用 Tabler 的 switch 样式，通过 CSS 控制)
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # 颜色字段
            'material_color_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：哑光黑、亮白'}),
            'pantone_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：PANTONE 19-4052'}),
            'rgb_value': forms.TextInput(attrs={'class': 'form-control d-block', 'data-coloris': '', 'placeholder': '#FF5733', 'maxlength': 7}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['scenarios'].queryset = ApplicationScenario.objects.all()
        self.fields['characteristics'].queryset = MaterialCharacteristic.objects.all()


class MaterialDataPointForm(TablerFormMixin, forms.ModelForm):
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))
    min_value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-min-select no-tomselect', 'style': 'display:none;'}))
    max_value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-max-select no-tomselect', 'style': 'display:none;'}))

    class Meta:
        model = MaterialDataPoint
        fields = ['test_config', 'value', 'value_text', 'min_value', 'max_value', 'min_value_text', 'max_value_text', 'remark']
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'style': 'width: 550px;', 'onchange': 'toggleValueInput(this)'}),
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}),
            'min_value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-min'}),
            'max_value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-max'}),
            'min_value_text': forms.TextInput(attrs={'class': 'form-control value-min-text', 'style': 'display:none;'}),
            'max_value_text': forms.TextInput(attrs={'class': 'form-control value-max-text', 'style': 'display:none;'}),
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['test_config'].queryset = TestConfig.objects.select_related('category').order_by('category__order', 'order')

        # 所有 select 变体无条件隐藏，仅 SELECT 类型时打开
        self.fields['value_select'].widget.attrs['style'] = 'display:none;'
        self.fields['min_value_select'].widget.attrs['style'] = 'display:none;'
        self.fields['max_value_select'].widget.attrs['style'] = 'display:none;'

        if self.instance and self.instance.pk:
            dtype = self.instance.test_config.data_type
            if dtype == 'TEXT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:block;'
                self.fields['min_value'].widget.attrs['style'] = 'display:none;'
                self.fields['max_value'].widget.attrs['style'] = 'display:none;'
                self.fields['min_value_text'].widget.attrs['style'] = 'display:block;'
                self.fields['max_value_text'].widget.attrs['style'] = 'display:block;'
            elif dtype == 'SELECT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['value_select'].widget.attrs['style'] = 'display:block;'
                self.fields['min_value'].widget.attrs['style'] = 'display:none;'
                self.fields['max_value'].widget.attrs['style'] = 'display:none;'
                self.fields['min_value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['max_value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['min_value_select'].widget.attrs['style'] = 'display:block;'
                self.fields['max_value_select'].widget.attrs['style'] = 'display:block;'
                options = self.instance.test_config.get_options_list()
                self.fields['value_select'].choices = [(opt, opt) for opt in options]
                self.fields['value_select'].initial = self.instance.value_text
                self.fields['value_select'].widget.attrs['data-current-value'] = self.instance.value_text
                self.fields['min_value_select'].choices = [(opt, opt) for opt in options]
                self.fields['max_value_select'].choices = [(opt, opt) for opt in options]
                self.fields['min_value_select'].initial = self.instance.min_value_text
                self.fields['max_value_select'].initial = self.instance.max_value_text
            else:
                # NUMBER: NumberInput 默认可见，隐藏 text/select
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['min_value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['max_value_text'].widget.attrs['style'] = 'display:none;'

        if self.data:
            prefix = self.prefix or ''
            test_config_key = f"{prefix}-test_config" if prefix else "test_config"
            test_config_id = self.data.get(test_config_key)
            if test_config_id:
                try:
                    config = TestConfig.objects.get(pk=test_config_id)
                    if config.data_type == 'SELECT':
                        options = config.get_options_list()
                        self.fields['value_select'].choices = [(opt, opt) for opt in options]
                        self.fields['min_value_select'].choices = [(opt, opt) for opt in options]
                        self.fields['max_value_select'].choices = [(opt, opt) for opt in options]
                except (TestConfig.DoesNotExist, ValueError):
                    pass

    def clean(self):
        cleaned_data = super().clean()
        test_config = cleaned_data.get('test_config')
        if test_config:
            if test_config.data_type == 'SELECT':
                cleaned_data['value_text'] = cleaned_data.get('value_select')
                cleaned_data['min_value_text'] = cleaned_data.get('min_value_select')
                cleaned_data['max_value_text'] = cleaned_data.get('max_value_select')
            # min > max 校验仅对 NUMBER 类型
            if test_config.data_type == 'NUMBER':
                min_val = cleaned_data.get('min_value')
                max_val = cleaned_data.get('max_value')
                if min_val is not None and max_val is not None and min_val > max_val:
                    raise forms.ValidationError("最小值不能大于最大值")
        return cleaned_data


MaterialDataFormSet = inlineformset_factory(MaterialLibrary, MaterialDataPoint, form=MaterialDataPointForm, extra=0, can_delete=True)


class MaterialTypeForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialType
        fields = ['name', 'classification', 'description']
        widgets = {
            'classification': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class ApplicationScenarioForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ApplicationScenario
        fields = ['name', 'requirements']
        widgets = {
            'requirements': forms.Textarea(attrs={'rows': 3, 'placeholder': '例如：耐高温、抗冲击...'}),
        }

# 特征属性表单
class MaterialCharacteristicForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialCharacteristic
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '填写该特征的详细描述...'}),
        }


class TestConfigForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = TestConfig
        fields = ['category', 'name', 'name_en', 'standard', 'condition', 'unit', 'order', 'data_type', 'options_config']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'name_en': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如: Tensile Strength'}),
            'order': forms.NumberInput(attrs={'placeholder': '排序权重，越小越靠前'}),
            'data_type': forms.Select(attrs={'class': 'form-select'}),
            'options_config': forms.Textarea(attrs={'rows': 2, 'placeholder': '仅当类型为选择时有效，用逗号分隔，如: V-0,V-1,HB'}),
        }
