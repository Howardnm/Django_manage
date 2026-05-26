class RelatedObjectRouter:
    """关联对象元数据路由器。

    供 app_workflow 内部使用，将审批流程的关联对象映射到其详情页 URL、
    显示名称和负责人。各业务模块在 apps.py 中调用 register() 完成注册，
    无需修改 app_workflow 代码。

    使用示例::

        from app_workflow.utils import related_object_router

        # 在业务模块的 apps.py 中注册
        related_object_router.register(
            MyModel,
            url_resolver=lambda obj: reverse('my_detail', kwargs={'pk': obj.pk}),
            display_name_resolver=lambda obj: obj.name,
            person_resolver=lambda obj: obj.manager,
        )

        # 在视图/模板中使用
        url = related_object_router.resolve(obj)
        name = related_object_router.get_display_name(obj)
        person = related_object_router.get_person(obj)
    """

    def __init__(self):
        self._registry = {}

    def register(self, model_class, url_resolver, *, display_name_resolver=None, person_resolver=None):
        """注册模型对应的元数据解析器。

        Parameters
        ----------
        model_class : Model class
            Django 模型类（非代理模型），会按 MRO 向上查找匹配。
        url_resolver : callable
            签名为 ``(obj) -> str | None``，接收模型实例，返回详情页 URL 或 None。
        display_name_resolver : callable, optional
            签名为 ``(obj) -> str``，返回对象的显示名称。未提供时回退到 str(obj)。
        person_resolver : callable, optional
            签名为 ``(obj) -> User | None``，返回对象的负责人/提交人。
        """
        self._registry[model_class] = {
            'url': url_resolver,
            'display_name': display_name_resolver,
            'person': person_resolver,
        }

    def _get_entry(self, obj):
        """按 MRO 顺序查找第一个匹配的注册项"""
        if obj is None:
            return None
        for cls in type(obj).__mro__:
            entry = self._registry.get(cls)
            if entry:
                return entry
        return None

    def resolve(self, obj):
        """解析关联对象的详情页 URL。"""
        entry = self._get_entry(obj)
        if entry:
            return entry['url'](obj)
        return None

    def get_display_name(self, obj):
        """解析关联对象的显示名称。未注册 display_name_resolver 时回退到 str(obj)。"""
        entry = self._get_entry(obj)
        if entry and entry['display_name']:
            return entry['display_name'](obj)
        return str(obj) if obj else None

    def get_person(self, obj):
        """解析关联对象的负责人/提交人。未注册 person_resolver 时返回 None。"""
        entry = self._get_entry(obj)
        if entry and entry['person']:
            return entry['person'](obj)
        return None


# 模块级单例，供各业务模块注册和视图调用
related_object_router = RelatedObjectRouter()
