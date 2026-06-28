"""
通用表单组件 — 可跨 app 复用的 Widget 和 Form Mixin。

当前组件：
- UserPickerWidget: 人员选择器（组织架构树），支持单选/多选
"""

from django import forms
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string


class UserPickerWidget(forms.TextInput):
    """
    人员选择器 widget — 通过组织架构树选择人员。

    渲染为：隐藏 input（存 value） + 只读 display input（显 label） + 按钮。
    点击按钮弹出 body 级 overlay，选中后回写。

    用法:
        # 在普通 Form 中
        owner = forms.CharField(
            widget=UserPickerWidget(multi=False),
            required=False,
        )

        # 在 FilterSet 中
        owner = django_filters.CharFilter(
            method='filter_owner',
            widget=UserPickerWidget(
                attrs={'placeholder': '选择负责人'},
                multi=False,
            ),
        )
    """

    template_name = 'includes/forms/user_picker_widget.html'
    input_type = 'hidden'  # 对外表现为 hidden input

    def __init__(self, attrs=None, multi=False, title='选择人员'):
        default_attrs = {'data-picker-widget': '1'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)
        self.multi = multi
        self.title = title

    def render(self, name, value, attrs=None, renderer=None):
        """使用自定义模板渲染，绕过默认 <input> 渲染。"""
        context = {
            'name': name,
            'value': value or '',
            'display_value': self._get_display_value(value),
            'multi': self.multi,
            'title': self.title,
            'attrs': self.build_attrs(self.attrs, attrs) if attrs else self.attrs,
        }
        return mark_safe(render_to_string(self.template_name, context))

    def _get_display_value(self, value):
        """给定 value（用户 ID 或 逗号分隔的 IDs），尝试获取 display label。"""
        if not value:
            return ''
        # 简单返回 raw value — JS 会在 confirm 时写入 display
        # 如需回显历史选中值，由调用方通过 Widget 的 value_from_datadict 处理
        return ''

    class Media:
        css = {'all': ['css/common/user_picker_modal.css']}
        js = ['js/common/user_picker_modal.js']
