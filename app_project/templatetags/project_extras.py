from django import template
from urllib.parse import urlencode

register = template.Library()


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """
    用于在模板链接中保留当前的 URL 参数（如 q=xxx, sort=xxx），并更新指定的参数（如 page=2）。
    用法：{% url_replace page=page_obj.next_page_number %}
    """
    query = context['request'].GET.copy()

    for key, value in kwargs.items():
        query[key] = value

    return query.urlencode()


@register.filter
def sort_toggle(field_name, current_sort):
    """
    (旧版单选逻辑，保留兼容)
    """
    if current_sort == field_name:
        return f"-{field_name}"
    else:
        return field_name


@register.simple_tag(takes_context=True)
def sort_url_multi(context, field):
    """
    【新增】多字段排序链接生成器
    逻辑：
    1. 获取当前所有 sort 参数
    2. 如果 field 不在其中，追加 sort=field
    3. 如果 field 在其中，变为 sort=-field
    4. 如果 -field 在其中，移除该排序 (取消)
    """
    request = context['request']
    query = request.GET.copy()
    
    # 获取当前的排序列表 (list)
    current_sorts = query.getlist('sort')
    
    new_sorts = []
    found = False
    
    for s in current_sorts:
        if s == field:
            # 正序 -> 倒序
            new_sorts.append(f"-{field}")
            found = True
        elif s == f"-{field}":
            # 倒序 -> 移除 (取消排序)
            found = True
            # 不添加到 new_sorts
        else:
            # 其他字段保持不变
            new_sorts.append(s)
            
    if not found:
        # 未找到 -> 追加正序
        new_sorts.append(field)
        
    # 更新 query 中的 sort 参数
    query.setlist('sort', new_sorts)
    
    return query.urlencode()
