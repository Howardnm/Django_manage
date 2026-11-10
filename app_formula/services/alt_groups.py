"""配方替代组。一组里的每一行都是该位置的完整份数，合计只算一次。"""

import re
from decimal import Decimal
from types import SimpleNamespace

_GROUP = re.compile(r'^[0-9A-Z]{1,2}$')
_HUNDRED = Decimal('100')
_PCT = Decimal('0.000001')
_USAGE = Decimal('0.01')


class AltGroupError(Exception):
    """一组的行放在一起看不合法。"""


def _value(row, name):
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _text(row, name):
    value = _value(row, name)
    return '' if value is None else str(value).strip()


def _raw_id(row):
    raw = _value(row, 'raw_material')
    if raw is None:
        return _value(row, 'raw_material_id')
    return raw.pk if hasattr(raw, 'pk') else raw


def _blank(value):
    return value is None or value == ''


def validate_alt_rows(rows):
    """同一替代组至少两行，份数相同、策略相同。

    策略 1 只收使用可能性，合计 100，优先级留空。
    策略 2 只收优先级，从 1 连续排，使用可能性留空。
    没有替代组的行，另外三列必须空。
    """
    buckets = {}
    for row in rows:
        group = _text(row, 'alt_group').upper()
        strategy = _text(row, 'alt_strategy')
        priority = _value(row, 'alt_priority')
        usage = _value(row, 'usage_percent')
        if not group:
            if strategy or not _blank(priority) or not _blank(usage):
                raise AltGroupError('没有替代组时，策略、优先级和使用可能性都要留空。')
            continue
        if not _GROUP.match(group):
            raise AltGroupError(f'替代组「{group}」只能是 1 到 2 位数字或大写字母。')
        if strategy not in ('1', '2'):
            raise AltGroupError(f'替代组 {group} 要选择策略。')
        buckets.setdefault(group, []).append(SimpleNamespace(
            raw_id=_raw_id(row),
            strategy=strategy,
            priority=priority,
            usage=None if _blank(usage) else Decimal(str(usage)),
            percentage=Decimal(str(_value(row, 'percentage') or 0)),
        ))

    for group, members in buckets.items():
        if len(members) < 2:
            raise AltGroupError(f'替代组 {group} 至少要两种原料。')
        if len(members) > 3:
            raise AltGroupError(f'替代组 {group} 最多三种原料。')
        if len({member.raw_id for member in members}) != len(members):
            raise AltGroupError(f'替代组 {group} 里原料不能重复。')
        if len({member.strategy for member in members}) != 1:
            raise AltGroupError(f'替代组 {group} 的策略必须相同。')
        shares = {member.percentage.quantize(_PCT) for member in members}
        if len(shares) != 1:
            raise AltGroupError(f'替代组 {group} 的份数必须相同。')
        if members[0].strategy == '1':
            if any(not _blank(member.priority) for member in members):
                raise AltGroupError(f'替代组 {group} 按用途可能性时不要填优先级。')
            if any(member.usage is None for member in members):
                raise AltGroupError(f'替代组 {group} 每一行都要填使用可能性。')
            total = sum((member.usage for member in members), Decimal('0')).quantize(_USAGE)
            if total != _HUNDRED:
                raise AltGroupError(f'替代组 {group} 的使用可能性要合计 100，现在是 {total}。')
            continue
        if any(member.usage is not None for member in members):
            raise AltGroupError(f'替代组 {group} 按 100% 检查时不要填使用可能性。')
        priorities = []
        for member in members:
            if member.priority in (None, ''):
                raise AltGroupError(f'替代组 {group} 每一行都要填优先级。')
            priorities.append(int(member.priority))
        if set(priorities) != set(range(1, len(members) + 1)):
            raise AltGroupError(f'替代组 {group} 的优先级要从 1 连续排到 {len(members)}。')


def collapse_cost_pairs(lines, price_of):
    """把一组收成一份再交给成本内核。

    策略 1 的单价按使用可能性加权。策略 2 用优先级 1 的单价。
    没有替代组的行原样返回。
    """
    pairs = []
    grouped = {}
    for line in lines:
        group = (getattr(line, 'alt_group', None) or '').strip()
        if not group:
            pairs.append((line.percentage, price_of(line)))
            continue
        grouped.setdefault(group, []).append(line)
    for members in grouped.values():
        percentage = members[0].percentage
        if (members[0].alt_strategy or '') == '2':
            primary = min(members, key=lambda item: item.alt_priority or 99)
            pairs.append((percentage, price_of(primary)))
            continue
        total_price = Decimal('0')
        missing = False
        for line in members:
            price = price_of(line)
            if price is None:
                pairs.append((percentage, None))
                missing = True
                break
            usage = Decimal(str(line.usage_percent or 0))
            total_price += Decimal(str(price)) * usage / _HUNDRED
        if not missing:
            pairs.append((percentage, total_price))
    return pairs


def dose_shares(lines):
    """试产实际领用的 (行, 份数)。

    策略 2 只领优先级 1，份数是完整的那一份。
    策略 1 按使用可能性拆开，加起来仍是这一份。
    一组留在第一次出现的位置，不挪到表尾。
    """
    grouped = {}
    for line in lines:
        group = (getattr(line, 'alt_group', None) or '').strip()
        if group:
            grouped.setdefault(group, []).append(line)
    doses = []
    emitted = set()
    for line in lines:
        group = (getattr(line, 'alt_group', None) or '').strip()
        if not group:
            doses.append((line, Decimal(str(line.percentage or 0))))
            continue
        if group in emitted:
            continue
        emitted.add(group)
        members = grouped[group]
        if (members[0].alt_strategy or '') == '2':
            primary = min(members, key=lambda item: item.alt_priority or 99)
            doses.append((primary, Decimal(str(primary.percentage or 0))))
            continue
        for member in members:
            usage = Decimal(str(member.usage_percent or 0))
            share = Decimal(str(member.percentage or 0)) * usage / _HUNDRED
            doses.append((member, share))
    return doses


def dose_index(lines):
    """(原料, 喂料口) → 实际领用份数。同一位置不会有两笔。"""
    return {
        (line.raw_material_id, line.feeding_port): share
        for line, share in dose_shares(lines)
    }
