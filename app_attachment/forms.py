"""
附件上传表单
"""
from django import forms

from common_utils.filters import TablerFormMixin
from .models import Attachment

# 未单独限制扩展名的业务沿用这份列表（文档、图片、压缩包、CAD）
_DEFAULT_ACCEPT = (
    '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,'
    '.jpg,.jpeg,.png,.gif,.bmp,.webp,.svg,'
    '.txt,.csv,.zip,.rar,.7z,.stp,.step,.igs,.iges,.dwg,.dxf'
)


class AttachmentUploadForm(TablerFormMixin, forms.ModelForm):
    """
    通用附件上传表单。

    通过传入 config (AttachmentConfig) 动态设置
    文件分类选项和上传限制。
    """

    group_key = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Attachment
        fields = ['file', 'display_name', 'category', 'group_key', 'version', 'description']
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': '文件描述（选填）',
            }),
            'version': forms.NumberInput(attrs={
                'min': 1,
                'placeholder': '版本号',
            }),
            'display_name': forms.TextInput(attrs={
                'placeholder': '留空则使用文件名',
            }),
        }

    def __init__(self, *args, **kwargs):
        # 取出 config 参数，不传给父类
        config = kwargs.pop('config', None)
        self.attachment_config = config
        super().__init__(*args, **kwargs)

        # 根据配置动态设置分类选项
        if config and config.categories:
            self.fields['category'].widget = forms.Select(attrs={
                'class': 'form-select',
            })
            self.fields['category'].widget.choices = config.categories
            if config.categories:
                self.fields['category'].initial = config.categories[0][0]
            self.fields['category'].required = False

        # 文件字段样式。配了 allowed_extensions 的业务只接受那些后缀
        self.fields['file'].widget.attrs.update({
            'class': 'form-control',
            'accept': self._accept_value(config),
        })

    @staticmethod
    def _accept_value(config):
        """浏览器文件选择框的 accept。服务端仍以 clean_file 为准。"""
        if config and config.allowed_extensions:
            return ','.join(
                f".{ext.lower().lstrip('.')}" for ext in config.allowed_extensions
            )
        return _DEFAULT_ACCEPT

    def clean_file(self):
        """扩展名限制只在配置声明了 allowed_extensions 时生效。"""
        uploaded = self.cleaned_data.get('file')
        config = self.attachment_config
        if uploaded and config and not config.allows_filename(getattr(uploaded, 'name', '')):
            allowed = '、'.join(config.allowed_extensions)
            raise forms.ValidationError(f"只允许上传这些格式：{allowed}。")
        return uploaded
