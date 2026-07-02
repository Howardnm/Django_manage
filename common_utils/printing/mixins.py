"""
打印视图 Mixin。

提供 PrintableMixin — 可混入任何 Django CBV，为其增加打印 HTML 响应能力。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import HttpResponse

if TYPE_CHECKING:
    from .base import BasePrintRenderer


class PrintableMixin:
    """CBV Mixin — 为 View 增加打印响应能力。

    用法::

        class MyPrintView(PrintableMixin, DetailView):
            model = MyModel
            renderer_class = MyRenderer

            def get(self, request, *args, **kwargs):
                self.object = self.get_object()
                return self.render_print_response()
    """

    renderer_class: type[BasePrintRenderer] | None = None

    def get_print_renderer(self) -> BasePrintRenderer:
        """实例化并返回打印渲染器。

        子类可覆盖此方法以传递额外参数给 Renderer 构造函数。
        """
        if self.renderer_class is None:
            raise ValueError(
                f'{self.__class__.__name__} 必须设置 renderer_class 类属性'
            )
        return self.renderer_class()

    def render_print_response(self) -> HttpResponse:
        """渲染打印 HTML 并返回 Django HttpResponse。

        Returns:
            HttpResponse: 已渲染的 HTML 文档（Content-Type: text/html）
        """
        renderer = self.get_print_renderer()
        html = renderer.render_html()
        return HttpResponse(html)
