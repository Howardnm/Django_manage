"""
通用自动补全注册表 — 解耦 common_utils 与各 app。

各 app 在 AppConfig.ready() 中调用 register_autocomplete() 注册自己的
模型类型、查询构建器和格式化器。common_utils/views.py 的 MaterialAutocompleteView
通过 get_registry() 查找，无需导入任何 app 模块。

用法（在 app 的 apps.py 中）：
    from common_utils.autocomplete_registry import register_autocomplete

    def _build_qs(query):
        from myapp.models import MyModel
        return MyModel.objects.filter(name__icontains=query)

    def _format(item):
        return {'value': item.pk, 'text': str(item)}

    register_autocomplete('my_model', _build_qs, _format, 'my_model_detail')
"""

_registry = {}


def register_autocomplete(model_key, builder_fn, formatter_fn, detail_url_name=None):
    """
    注册一个模型类型的自动补全处理器。

    Args:
        model_key: 字符串键（如 'material', 'project', 'user'）
        builder_fn: 函数 (query: str) -> QuerySet，用于构建查询
        formatter_fn: 函数 (item) -> {'value': ..., 'text': ...}，格式化单个结果
        detail_url_name: 可选的 Django URL 名称，用于生成详情页链接
    """
    _registry[model_key] = {
        'builder': builder_fn,
        'formatter': formatter_fn,
        'detail_url': detail_url_name,
    }


def get_registry():
    """返回当前注册表（供 MaterialAutocompleteView 使用）。"""
    return _registry
