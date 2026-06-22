"""
状态转换守卫引擎 — 基于注册模式，支持跨 app 使用。

用法:
    # 在 apps.py ready() 中注册
    from common_utils.state_machine import StateMachine
    StateMachine.register(ProductionOrder, {
        'DRAFT': ['WORKFLOW_RUNNING', 'CANCELED'],
        'WORKFLOW_RUNNING': ['ACCEPTED', 'DRAFT', 'CANCELED'],
        'ACCEPTED': ['EXTRUDING'],
        'EXTRUDING': ['INJECTION_MOLDING', 'COMPLETED'],
        'INJECTION_MOLDING': ['TESTING'],
        'TESTING': ['COMPLETED'],
        'COMPLETED': [],
        'CANCELED': [],
    })

    # 使用
    StateMachine.transition(order, 'ACCEPTED', user)
    StateMachine.can_transition(order, 'ACCEPTED')
    StateMachine.get_allowed_transitions(order)
"""

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


class InvalidStateTransition(Exception):
    """非法状态转换异常"""

    def __init__(self, obj, current_status, target_status):
        self.obj = obj
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"{obj.__class__.__name__} 不允许从 {current_status} 转换到 {target_status}"
        )


class StateMachine:
    """
    状态转换守卫引擎 — 规则表驱动，基于注册模式。

    各 app 在 AppConfig.ready() 中调用 StateMachine.register() 注册模型的状态转换规则。
    """

    # model_class.__name__ → {from_status: [allowed_to_statuses]}
    _TRANSITIONS_MAP = {}

    @classmethod
    def register(cls, model_class, transitions):
        """
        注册模型的状态转换规则。

        Args:
            model_class: Django Model 类
            transitions: dict of {from_status: [allowed_to_statuses]}
                         例如: {'PENDING': ['IN_PROGRESS'], 'IN_PROGRESS': ['COMPLETED'], 'COMPLETED': []}
        """
        cls._TRANSITIONS_MAP[model_class.__name__] = transitions
        logger.info(f"[StateMachine] Registered {model_class.__name__} with {len(transitions)} states")

    @classmethod
    def transition(cls, obj, target_status, user=None):
        """
        执行状态转换，包含守卫条件检查。

        Args:
            obj: 模型实例
            target_status: 目标状态字符串
            user: 操作用户（用于日志记录）

        Raises:
            InvalidStateTransition: 当前状态不允许转换到目标状态
        """
        model_name = obj.__class__.__name__
        transitions = cls._TRANSITIONS_MAP.get(model_name)

        if transitions is None:
            raise ValueError(f"未注册状态机的模型: {model_name}，请在 AppConfig.ready() 中调用 StateMachine.register()")

        current_status = obj.status
        allowed = transitions.get(current_status, [])

        if target_status not in allowed:
            raise InvalidStateTransition(obj, current_status, target_status)

        # 执行转换
        old_status = obj.status
        obj.status = target_status

        # 更新时间戳
        if target_status == 'COMPLETED' and hasattr(obj, 'completed_at'):
            obj.completed_at = timezone.now()
        if target_status in ('IN_PROGRESS',) and hasattr(obj, 'started_at'):
            if obj.started_at is None:
                obj.started_at = timezone.now()

        obj.save()

        user_info = f" by {user}" if user else ""
        logger.info(
            f"[StateMachine] {model_name} {obj} : "
            f"{old_status} → {target_status}{user_info}"
        )

        return obj

    @classmethod
    def can_transition(cls, obj, target_status):
        """检查是否允许转换到目标状态（不执行转换）"""
        model_name = obj.__class__.__name__
        transitions = cls._TRANSITIONS_MAP.get(model_name)
        if transitions is None:
            return False
        return target_status in transitions.get(obj.status, [])

    @classmethod
    def get_allowed_transitions(cls, obj):
        """获取当前状态允许的所有转换"""
        model_name = obj.__class__.__name__
        transitions = cls._TRANSITIONS_MAP.get(model_name)
        if transitions is None:
            return []
        return transitions.get(obj.status, [])
