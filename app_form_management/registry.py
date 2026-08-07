from app_project.models import Project, ProjectNode
from app_workflow.utils import related_object_router


class TargetConfig:
    """注册表条目 — 封装目标模型的展示行为"""
    __slots__ = ('model', 'label', '_display')

    def __init__(self, model, label, display=None):
        self.model = model
        self.label = label
        self._display = display

    def display(self, obj):
        if self._display:
            return self._display(obj)
        return str(obj)


class ProjectTarget(Project):
    class Meta:
        proxy = True


class ProjectNodeTarget(ProjectNode):
    class Meta:
        proxy = True


# 别名 → TargetConfig（扩展只需新增一条记录）
_TARGET_REGISTRY = {
    'project': TargetConfig(
        model=ProjectTarget,
        label='项目',
        display=lambda obj: obj.name,
    ),
    'project-node': TargetConfig(
        model=ProjectNodeTarget,
        label='项目节点',
        display=lambda obj: f'{obj.project.name} — {obj.get_stage_display()} (第{obj.round}轮)',
    ),
}

# 反向映射：原始模型 → 别名
_MODEL_TO_ALIAS = {cfg.model.__bases__[0]: alias for alias, cfg in _TARGET_REGISTRY.items()}


def get_target(alias):
    cfg = _TARGET_REGISTRY.get(alias)
    return cfg.model if cfg else None


def get_alias_for_model(model_class):
    return _MODEL_TO_ALIAS.get(model_class)


def get_module_choices():
    return [(alias, cfg.label) for alias, cfg in _TARGET_REGISTRY.items()]


def resolve_form_target(submission):
    """解析表单提交的关联业务对象，返回 (关联模块, 关联内容, 关联链接)。

    复用 _TARGET_REGISTRY（模块标签/内容展示）与 related_object_router（详情链接）。
    """
    if not submission.content_type_id:
        return '—', '—', None
    model_class = submission.content_type.model_class()
    cfg = _TARGET_REGISTRY.get(get_alias_for_model(model_class))
    module = cfg.label if cfg else str(submission.content_type)
    target_obj = submission.target_object
    display = cfg.display(target_obj) if cfg and target_obj else (str(target_obj) if target_obj else '—')
    return module, display, related_object_router.resolve(target_obj)
