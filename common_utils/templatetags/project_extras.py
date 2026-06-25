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
    Toggles sorting order for a given field.
    If current_sort is 'field_name', returns '-field_name'.
    If current_sort is '-field_name', returns 'field_name'.
    Otherwise, returns 'field_name'.
    """
    if current_sort == field_name:
        return f"-{field_name}"
    elif current_sort == f"-{field_name}": # 修复：正确判断是否为降序
        return field_name
    else:
        return field_name


from decimal import Decimal


@register.filter
def smart_decimal(value):
    """强制2位小数; 若第3位非0则显示3位"""
    if value is None:
        return '-'
    try:
        d = Decimal(str(value)).quantize(Decimal('0.001'))
    except Exception:
        return str(value)
    third = d.as_tuple().exponent  # e.g. -3 means 3 decimal places
    # 保留3位小数后，检查第3位是否为0
    if third == -3:
        # 第3位是否为0
        if d.as_tuple().digits[-1] == 0:
            return '{:.2f}'.format(d)
        else:
            return '{:.3f}'.format(d)
    # 不足3位，直接按2位显示
    return '{:.2f}'.format(d)


@register.filter
def get_item(d, key):
    """从字典中按键取值，模板中用法：{{ my_dict|get_item:key }}。
    自动尝试 int/str 两种键类型，兼容 JSON 反序列化后的字符串键。"""
    if d is None:
        return None
    try:
        if hasattr(d, 'get'):
            val = d.get(key)
            if val is not None:
                return val
            # JSON 反序列化后 key 是字符串，模板中常传整数
            alt_key = str(key) if isinstance(key, int) else (int(key) if isinstance(key, str) and key.isdigit() else None)
            if alt_key is not None:
                return d.get(alt_key)
            return None
        return d[key]
    except (KeyError, TypeError, IndexError):
        return None


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
    current_sorts = query.getlist('sort')
    
    new_sorts = []
    found = False
    for s in current_sorts:
        if s == field:
            new_sorts.append(f"-{field}")
            found = True
        elif s == f"-{field}":
            found = True
        else:
            new_sorts.append(s)
            
    if not found:
        new_sorts.append(field)
        
    query.setlist('sort', new_sorts)
    return query.urlencode()
