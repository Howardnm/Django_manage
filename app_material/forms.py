from django import forms
from django.forms import inlineformset_factory

from app_material.models import MaterialLibrary, ApplicationScenario, MaterialDataPoint, TestConfig, MaterialFile, MaterialType
from common_utils.filters import TablerFormMixin


class MaterialForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialLibrary
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            # 为 scenarios 字段添加懒加载属性，并指定为多选远程搜索
            'scenarios': forms.SelectMultiple(attrs={'class': 'form-select remote-search tomselect-multi-remote', 'data-model': 'applicationscenario'}),
            'flammability': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 【性能核心优化】
        # 如果没有 data (说明是 GET 请求渲染页面)，则清空 QuerySet，避免渲染成千上万个 option
        # 但是，必须保留 "当前已选" 的那个值，否则页面上显示为空
        if not self.data:
            instance = kwargs.get('instance')

            # 优化应用场景字段 (多对多)
            qs_scenarios = ApplicationScenario.objects.none()
            if instance and instance.pk:
                qs_scenarios = instance.scenarios.all()
            self.fields['scenarios'].queryset = qs_scenarios


class MaterialDataPointForm(TablerFormMixin, forms.ModelForm):
    # 动态添加的选择字段，用于 data_type='SELECT' 的情况
    # 注意：这里不要加 form-select-search，否则会被 Tom Select 初始化
    # TablerFormMixin 会自动加 form-select-search，除非我们在 Mixin 里做了排除，或者在这里覆盖 class
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = MaterialDataPoint
        fields = ['test_config', 'value', 'value_text', 'remark'] # 增加 value_text
        widgets = {
            # 开启搜索功能，方便快速查找 "ISO 527"
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            # 【修改】允许3位小数
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}), # 默认隐藏
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 【性能优化】预加载 TestConfig，避免 N+1 查询
        # 并且按分类排序，方便选择
        self.fields['test_config'].queryset = TestConfig.objects.select_related('category').order_by('category__order', 'order')

        # 如果是编辑状态，且当前数据是文本类型，则显示文本框，隐藏数字框
        if self.instance and self.instance.pk:
            dtype = self.instance.test_config.data_type
            if dtype == 'TEXT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:block;'
            elif dtype == 'SELECT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['value_select'].widget.attrs['style'] = 'display:block;'

                # 动态填充选项
                options = self.instance.test_config.get_options_list()
                self.fields['value_select'].choices = [(opt, opt) for opt in options]
                # 设置初始值
                self.fields['value_select'].initial = self.instance.value_text
                # 将当前值存入 data-current-value 属性，方便前端 JS 读取
                self.fields['value_select'].widget.attrs['data-current-value'] = self.instance.value_text

        # 【关键修复】如果是 POST 请求，必须重新填充 choices，否则 Django 验证会失败
        # 因为 ChoiceField 默认验证提交的值 must in choices 中
        if self.data:
            # 尝试从 POST 数据中获取 test_config ID
            # 字段名格式通常是: properties-0-test_config
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

        # 如果是选择类型，将选择的值赋给 value_text
        if test_config and test_config.data_type == 'SELECT':
            # 修复：即使 value_select 为空字符串，也要赋值给 value_text，以便清空
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


class TestConfigForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = TestConfig
        fields = ['category', 'name', 'standard', 'condition', 'unit', 'order', 'data_type', 'options_config'] # 增加 options_config
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'placeholder': '排序权重，越小越靠前'}),
            'data_type': forms.Select(attrs={'class': 'form-select'}),
            'options_config': forms.Textarea(attrs={'rows': 2, 'placeholder': '仅当类型为选择时有效，用逗号分隔，如: V-0,V-1,HB'}),
        }
