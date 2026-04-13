from django import forms
from django.forms import inlineformset_factory

from .models.material import (MaterialLibrary, ApplicationScenario, MaterialDataPoint, 
                               TestConfig, MaterialFile, MaterialType, MaterialCharacteristic)
from common_utils.filters import TablerFormMixin


class MaterialForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialLibrary
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'scenarios': forms.SelectMultiple(attrs={
                'class': 'form-select remote-search tomselect-multi-remote', 
                'data-model': 'scenario'
            }),
            'characteristics': forms.SelectMultiple(attrs={
                'class': 'form-select remote-search tomselect-multi-remote', 
                'data-model': 'characteristic' 
            }),
            'flammability': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data:
            instance = kwargs.get('instance')
            qs_scenarios = ApplicationScenario.objects.none()
            qs_characteristics = MaterialCharacteristic.objects.none()
            if instance and instance.pk:
                qs_scenarios = instance.scenarios.all()
                qs_characteristics = instance.characteristics.all()
            self.fields['scenarios'].queryset = qs_scenarios
            self.fields['characteristics'].queryset = qs_characteristics
        else:
            self.fields['scenarios'].queryset = ApplicationScenario.objects.all()
            self.fields['characteristics'].queryset = MaterialCharacteristic.objects.all()


class MaterialDataPointForm(TablerFormMixin, forms.ModelForm):
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = MaterialDataPoint
        fields = ['test_config', 'value', 'value_text', 'remark']
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}),
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['test_config'].queryset = TestConfig.objects.select_related('category').order_by('category__order', 'order')

        if self.instance and self.instance.pk:
            dtype = self.instance.test_config.data_type
            if dtype == 'TEXT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:block;'
            elif dtype == 'SELECT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['value_select'].widget.attrs['style'] = 'display:block;'
                options = self.instance.test_config.get_options_list()
                self.fields['value_select'].choices = [(opt, opt) for opt in options]
                self.fields['value_select'].initial = self.instance.value_text
                self.fields['value_select'].widget.attrs['data-current-value'] = self.instance.value_text

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
                except (TestConfig.DoesNotExist, ValueError):
                    pass

    def clean(self):
        cleaned_data = super().clean()
        test_config = cleaned_data.get('test_config')
        value_select = cleaned_data.get('value_select')
        if test_config and test_config.data_type == 'SELECT':
            cleaned_data['value_text'] = value_select
        return cleaned_data


MaterialDataFormSet = inlineformset_factory(MaterialLibrary, MaterialDataPoint, form=MaterialDataPointForm, extra=0, can_delete=True)


class MaterialFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialFile
        fields = ['file_type', 'file', 'version', 'description']
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': '版本变更说明...'}),
        }


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

# 新增：特征属性表单
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
        fields = ['category', 'name', 'standard', 'condition', 'unit', 'order', 'data_type', 'options_config']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'placeholder': '排序权重，越小越靠前'}),
            'data_type': forms.Select(attrs={'class': 'form-select'}),
            'options_config': forms.Textarea(attrs={'rows': 2, 'placeholder': '仅当类型为选择时有效，用逗号分隔，如: V-0,V-1,HB'}),
        }
