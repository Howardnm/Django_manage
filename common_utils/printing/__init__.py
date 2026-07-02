"""
通用打印框架 — 面向对象的 HTML 打印渲染体系。

Public API:
    from common_utils.printing import (
        BasePrintRenderer,   # 抽象基类 — 所有打印渲染器的父类
        PrintConfig,         # A4 打印配置 dataclass
        PrintableMixin,      # CBV Mixin — 为 View 增加打印响应能力
    )

架构：
    BasePrintRenderer (ABC)
        ├── render_html()        → Django template → HTML 字符串
        ├── get_context_data()   → 子类必须实现，返回模板上下文
        └── template_name        → 子类必须指定

    PrintableMixin (CBV Mixin)
        ├── renderer_class       → 指定使用的 Renderer 类
        ├── get_print_renderer() → 工厂方法，实例化 Renderer
        └── render_print_response() → 渲染 HTML 并返回 HttpResponse

扩展方式：
    1. 在业务 app 中创建子类继承 BasePrintRenderer
    2. 实现 get_context_data() 方法
    3. 在 View 中使用 PrintableMixin + renderer_class
"""

from .base import BasePrintRenderer, PrintConfig
from .mixins import PrintableMixin

__all__ = [
    'BasePrintRenderer',
    'PrintConfig',
    'PrintableMixin',
]
