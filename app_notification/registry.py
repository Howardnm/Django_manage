"""
通知类型注册表 — 纯通用注册原语。

只声明"通知类型长什么样" + 提供注册/查找原语，不含任何业务逻辑。
业务 app 在各自 app 的 notifications.py 中定义自己的通知类型并调用
register_ntype() 注册（通常在其 AppConfig.ready() 中导入触发），
通过 notify() 发送、register_signal_notification() 声明式绑定信号。

用法（供业务 app 定义类型）::

    from app_notification.registry import NotificationType, register_ntype

    register_ntype(NotificationType(
        code='myapp.event',
        label='我的事件',
        verb_template='{actor} 触发了「{display}」',
        recipients=my_recipients_fn,   # (context: dict) -> Iterable[User]
        url_resolver=my_url_fn,        # (target, context) -> str 可选
        icon='ti-bell',
    ))
"""
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from django.contrib.auth import get_user_model

User = get_user_model()


@dataclass(frozen=True)
class NotificationType:
    """通知类型定义。

    verb_template 的占位符由 notify() 传入的 context 提供；接收者/落地页
    解析函数接收同一份 context。type 注册后按 code 全局唯一。
    """
    code: str
    label: str
    verb_template: str
    # (context: dict) -> Iterable[User]，从上下文解析接收者
    recipients: Callable[[dict], Iterable]
    # (target, context) -> str，解析落地页 URL；未提供则落地页为空
    url_resolver: Optional[Callable] = None
    icon: str = 'ti-bell'
    channel: str = 'inbox'
    # 是否排除 actor 本人。通知"发起人关于审批人动作"（如通过/驳回）保留 True；
    # 通知"审批人有待办"（如提交/待办）须为 False，否则审批人==发起人时待办通知会被吞掉
    exclude_actor: bool = True


_registry: dict[str, NotificationType] = {}


def register_ntype(ntype: NotificationType) -> None:
    """注册一个通知类型。重复注册抛出 ValueError。"""
    if ntype.code in _registry:
        raise ValueError(f"通知类型重复注册: {ntype.code}")
    _registry[ntype.code] = ntype


def get_ntype(code: str) -> Optional[NotificationType]:
    """按编码查找通知类型，缺失返回 None。"""
    return _registry.get(code)


def get_registry() -> dict:
    """返回当前注册表（供测试/管理使用）。"""
    return _registry