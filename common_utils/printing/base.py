"""
打印渲染器抽象基类。

提供：
  - PrintConfig: A4 打印配置数据类
  - BasePrintRenderer: 所有打印渲染器的抽象父类
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from django.template.loader import render_to_string


@dataclass
class PrintConfig:
    """A4 打印页面配置。

    属性：
        page_size: 纸张规格，默认 'A4'
        orientation: 'portrait'（纵向）或 'landscape'（横向）
        margin_*: 页边距
        font_size: 基础字号
    """

    page_size: str = 'A4'
    orientation: str = 'portrait'
    margin_top: str = '8mm'
    margin_bottom: str = '8mm'
    margin_left: str = '6mm'
    margin_right: str = '6mm'
    font_size: str = '11px'

    # ── 派生值 ──
    @property
    def page_style(self) -> str:
        """生成 CSS @page 规则字符串"""
        return (
            f'@page {{ size: {self.page_size} {self.orientation}; '
            f'margin: {self.margin_top} {self.margin_right} '
            f'{self.margin_bottom} {self.margin_left}; }}'
        )


class BasePrintRenderer(ABC):
    """打印渲染器抽象基类。

    子类必须：
      1. 设置 template_name 类属性（或覆盖 get_template_name()）
      2. 实现 get_context_data() 方法

    用法::

        class MyRenderer(BasePrintRenderer):
            template_name = 'my_app/print.html'

            def __init__(self, obj, **kwargs):
                super().__init__(**kwargs)
                self.obj = obj

            def get_context_data(self, **kwargs):
                return {'data': self.obj}
    """

    template_name: str = ''
    config: PrintConfig

    def __init__(self, config: PrintConfig | None = None) -> None:
        self.config = config or PrintConfig()

    def get_template_name(self) -> str:
        """返回模板路径。覆盖此方法可实现动态模板切换。"""
        return self.template_name

    @abstractmethod
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """构建模板上下文。子类必须实现。

        Returns:
            dict[str, Any]: 传入模板的上下文变量，通常包含：
                - config: PrintConfig 实例（自动注入）
        """
        raise NotImplementedError

    def render_html(self, extra_context: dict[str, Any] | None = None) -> str:
        """渲染为 HTML 字符串。

        Args:
            extra_context: 额外的上下文变量，会合并到 get_context_data() 结果中

        Returns:
            str: 完整的 HTML 文档字符串
        """
        context = self.get_context_data()
        context.setdefault('config', self.config)
        if extra_context:
            context.update(extra_context)
        return render_to_string(self.get_template_name(), context)
