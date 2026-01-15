from django import template
from urllib.parse import urlencode

register = template.Library()


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """
    用于在模板链接中保留当前的 URL 参数（如 q=xxx, sort=xxx），并更新指定的参数（如 page=2）。
    用法：{% url_replace page=page_obj.next_page_number %}
    """
    query = context['request'].GET.dict()
    query.update(kwargs)
    return urlencode(query)


@register.filter
def sort_toggle(field_name, current_sort):
    """
    生成反转排序的参数值
    如果当前是 name，返回 -name
    如果当前是 -name，返回 name
    如果当前是其他，返回 name (默认正序)
    """
    if current_sort == field_name:
        return f"-{field_name}"
    else:
        # 包括 current_sort == f"-{field_name}" 的情况，也返回正序
        return field_name
