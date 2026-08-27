"""
附件上传表单
"""
from django import forms

from common_utils.filters import TablerFormMixin
from .models import Attachment


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

        # 文件字段样式
        self.fields['file'].widget.attrs.update({
            'class': 'form-control',
            'accept': self._get_accept_types(),
        })

    @staticmethod
    def _get_accept_types():
        """返回文件上传的 accept 属性值（常见的文档/图片格式）"""
        return (
            '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,'
            '.jpg,.jpeg,.png,.gif,.bmp,.webp,.svg,'
            '.txt,.csv,.zip,.rar,.7z,.stp,.step,.igs,.iges,.dwg,.dxf'
        )
