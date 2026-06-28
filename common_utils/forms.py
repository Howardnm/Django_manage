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
        """给定 value（用户 ID 或逗号分隔的 IDs），查询数据库获取 display label。

        解决 GET 请求带参数重新加载页面时，display input 为空的问题。
        """
        if not value:
            return ''
        from django.contrib.auth import get_user_model
        User = get_user_model()
        ids = [int(v) for v in str(value).split(',') if v.strip().isdigit()]
        if not ids:
            return ''
        users = list(User.objects.filter(pk__in=ids).only('pk', 'username', 'first_name'))
        if not users:
            return ''
        if self.multi:
            return f'{len(users)}人已选'
        u = users[0]
        return f'{u.first_name or u.username} ({u.username})'

    class Media:
        css = {'all': ['css/common/user_picker_modal.css']}
        js = ['js/common/user_picker_modal.js']
