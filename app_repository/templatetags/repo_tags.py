from django import template

register = template.Library()


@register.simple_tag
def get_category_color(category_name):
    """
    根据指标分类名称返回对应的 Tabler 颜色代码
    """
    if not category_name:
        return 'secondary'

    name = category_name.strip()
    if '物理' in name: return 'blue'
    if '机械' in name: return 'orange'
    if '热学' in name: return 'red'
    if '阻燃' in name or '电气' in name: return 'yellow'

    return 'secondary'