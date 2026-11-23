"""文本查询：普通包含匹配，或 * / ? 通配符。

``*`` 是任意长度，``?`` 是一个字符。其余字符按字面量，
大小写不区分。没有通配符时仍是各字段分别包含匹配。
有通配符时把字段按传入顺序用空格拼成一段，再对这一段匹配。
不在用户输入首尾自动补 ``*``。
"""

import re

from django.db.models import CharField, Q, Value
from django.db.models.functions import Coalesce, Concat


def text_q(qs, query, *fields):
    """按 fields 过滤 qs。无通配符时各字段包含匹配；有则拼成一段再匹配。"""
    # 连续星号收成一个，避免 pp**500n 被当成两段通配。
    query = re.sub(r'\*+', '*', query)
    if '*' not in query and '?' not in query:
        matched = Q()
        for field in fields:
            matched |= Q(**{f'{field}__icontains': query})
        return qs.filter(matched)
    # 不在首尾锚定。模式只要在拼出来的文字里出现即可，
    # 这样编码在后半段时 RM-000* 仍能命中，500N 后面还有文字时 PP*500n 也能命中。
    pattern = re.escape(query).replace(r'\*', '.*').replace(r'\?', '.')
    parts = []
    for index, field in enumerate(fields):
        if index:
            parts.append(Value(' '))
        parts.append(Coalesce(field, Value('')))
    if len(parts) == 1:
        parts.append(Value(''))
    return qs.annotate(
        _text_search=Concat(*parts, output_field=CharField())
    ).filter(_text_search__iregex=pattern)
