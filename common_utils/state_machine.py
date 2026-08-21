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
from django.db import transaction
from django.dispatch import Signal
from django.utils import timezone

logger = logging.getLogger(__name__)

# 状态转换成功信号 — 跨 app 通用，发出参数: obj, old_status, user
# 各 app 可在 AppConfig.ready() 中监听，用于状态变更后的联动（如发通知）。
state_changed = Signal()


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
    # model_class.__name__ → {started: 'field_name', completed: 'field_name'}
    _TIMESTAMP_FIELDS = {}

    @classmethod
    def register(cls, model_class, transitions, timestamp_fields=None):
        """
        注册模型的状态转换规则。

        Args:
            model_class: Django Model 类
            transitions: dict of {from_status: [allowed_to_statuses]}
                         例如: {'PENDING': ['IN_PROGRESS'], 'IN_PROGRESS': ['COMPLETED'], 'COMPLETED': []}
            timestamp_fields: dict of {started: 'field_name', completed: 'field_name'}
                         可选，默认 {'started': 'started_at', 'completed': 'completed_at'}
        """
        cls._TRANSITIONS_MAP[model_class.__name__] = transitions
        cls._TIMESTAMP_FIELDS[model_class.__name__] = timestamp_fields or {
            'started': 'started_at', 'completed': 'completed_at',
        }
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

        old_status = current_status
        model_class = type(obj)

        # 构建原子更新字段（compare-and-swap: WHERE status = current_status）
        update_fields = {'status': target_status}

        # 更新时间戳（使用注册时配置的字段名）
        tsf = cls._TIMESTAMP_FIELDS.get(model_name, {
            'started': 'started_at', 'completed': 'completed_at',
        })
        if target_status == 'COMPLETED':
            completed_field = tsf.get('completed', 'completed_at')
            if hasattr(obj, completed_field):
                update_fields[completed_field] = timezone.now()
        if target_status in ('IN_PROGRESS',):
            started_field = tsf.get('started', 'started_at')
            if hasattr(obj, started_field) and getattr(obj, started_field) is None:
                update_fields[started_field] = timezone.now()

        # 原子更新：只有状态未被其他事务修改时才生效（compare-and-swap）
        updated = model_class.objects.filter(
            pk=obj.pk, status=current_status
        ).update(**update_fields)

        if not updated:
            raise InvalidStateTransition(obj, current_status, target_status)

        # 同步内存中的对象状态
        obj.status = target_status
        completed_field = tsf.get('completed', 'completed_at')
        if hasattr(obj, completed_field) and completed_field in update_fields:
            setattr(obj, completed_field, update_fields[completed_field])
        started_field = tsf.get('started', 'started_at')
        if hasattr(obj, started_field) and started_field in update_fields:
            setattr(obj, started_field, update_fields[started_field])

        user_info = f" by {user}" if user else ""
        logger.info(
            f"[StateMachine] {model_name} {obj} : "
            f"{old_status} → {target_status}{user_info}"
        )

        # 状态转换成功后发出信号，供各 app 联动（如通知项目成员）。
        # 延迟到事务提交后（transaction.on_commit）触发：保证任何非事务性
        # 副作用（邮件/外部 API/消息投递）只在事务真正落库、不会回滚时才执行；
        # 若当前不在事务中（autocommit），on_commit 回调会立即执行，行为不变。
        transaction.on_commit(
            lambda: state_changed.send(
                sender=model_class, obj=obj, old_status=old_status, user=user,
            )
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
