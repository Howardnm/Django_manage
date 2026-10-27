"""色粉页的 G/25KG 与库存份数换算。

库存 ``percentage`` 仍是每 100 kg 主配方加多少 kg 色粉。
配色页填写和展示的是每 25 kg 基料加多少克：克 = 份数 × 250。
"""

from decimal import Decimal, ROUND_HALF_UP

GRAMS_PER_PART = Decimal('250')
# 3 位小数的克 ÷250，商最多 6 位小数，和 percentage 字段一致。
PART_QUANTUM = Decimal('0.000001')
GRAM_MAX_DIGITS = 15
GRAM_DECIMAL_PLACES = 3


def percentage_to_grams(percentage) -> Decimal:
    """份数折成每 25 kg 的克数。乘法是精确的，只去掉尾零。"""
    grams = Decimal(percentage) * GRAMS_PER_PART
    text = format(grams, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return Decimal(text or '0')


def grams_to_percentage(grams) -> Decimal:
    """克数折回份数。3 位以内的克数除完仍落在 6 位小数里，不会再被收短。"""
    return (Decimal(grams) / GRAMS_PER_PART).quantize(PART_QUANTUM, rounding=ROUND_HALF_UP)
