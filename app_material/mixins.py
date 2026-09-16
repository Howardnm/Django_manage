from django.contrib import messages
from django.utils.safestring import mark_safe

from app_user.mixins import UnifiedAccessMixin

class MaterialAccessMixin(UnifiedAccessMixin):
    """材料库模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'material'
    module_name = '材料成品库'
    module_description = '材料成品库。按创建人(creator)隔离。'
    user_link_fields = ['creator']


class MaterialFormErrorMixin:
    """把表单/表单集错误汇总成一条 message 回显。

    录入页的物性明细是 inline formset，其错误（如「最小值不能大于最大值」）落在
    子表单的 non_field_errors 上。模板只逐行渲染 value/test_config 的字段错误，
    不会渲染 `__all__`，因此这类错误必须经 messages 才能让用户看到 —— 否则表单
    静默弹回，用户不知道哪里填错了。

    新增页与编辑页都必须挂上：只在编辑页挂会让新增页的校验失败无声无息。
    """

    def _build_error_message(self, form, formset=None):
        """构建详细的字段错误信息"""
        lines = ['<strong>保存失败，请修正以下问题：</strong>']

        for field_name, errs in form.errors.items():
            label = form[field_name].label if field_name != '__all__' and field_name in form.fields else field_name
            for e in errs:
                lines.append(f'• {label}: {e}')

        if formset:
            for i, sf in enumerate(formset):
                if not sf.errors:
                    continue
                for field_name, errs in sf.errors.items():
                    if field_name == '__all__':
                        for e in errs:
                            lines.append(f'• 第{i+1}行: {e}')
                    else:
                        label = sf[field_name].label if field_name in sf.fields else field_name
                        for e in errs:
                            lines.append(f'• 第{i+1}行 {label}: {e}')

        return mark_safe('<br>'.join(lines))

    def form_invalid(self, form):
        """主表单自身校验失败时也要给出提示，否则同样是静默弹回。"""
        messages.error(self.request, self._build_error_message(form))
        return super().form_invalid(form)
