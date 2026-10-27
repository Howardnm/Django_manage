from django import template

from app_color_center.units import percentage_to_grams

register = template.Library()


@register.filter
def grams_per_25kg(value):
    """库存份数 → 每 25 kg 的克数，不额外收成 2～3 位。"""
    if value is None or value == '':
        return '-'
    try:
        return format(percentage_to_grams(value), 'f')
    except Exception:
        return str(value)
