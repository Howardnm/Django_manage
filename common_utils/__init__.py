"""
通用工具组件 — 跨 app 复用的基础设施。

Public API:
    from common_utils import (
        TablerFilterMixin,      # FilterSet 自动样式注入
        TablerFormMixin,        # Form 自动样式注入
        DateRangeFilterMixin,   # 日期范围筛选（created_at）
        UserPickerWidget,       # 人员选择器 Django Widget
        SearchPickerConfig,     # 搜索选择器配置类
    )

内部模块：
    autocomplete_registry  — 自动补全注册表（各 app 在 apps.py 中注册模型）
    state_machine          — 状态转换守卫引擎
"""

from common_utils.filters import TablerFilterMixin, TablerFormMixin, DateRangeFilterMixin  # noqa: F401
from common_utils.forms import UserPickerWidget  # noqa: F401
from common_utils.search_picker_config import SearchPickerConfig  # noqa: F401

