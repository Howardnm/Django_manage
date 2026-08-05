from app_project.models import Project, ProjectNode


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
