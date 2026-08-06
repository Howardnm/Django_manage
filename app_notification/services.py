"""
通知服务层 — 声明式发送通知。

业务模块在函数中调用 notify()（类似 django logging 的 logger.info()），
传入通知类型编码 + 目标对象 + 上下文，接收者由注册表解析。
"""
import logging

from .models import Notification
from .registry import get_ntype

logger = logging.getLogger(__name__)


def notify(code: str, *, target=None, action_object=None, actor=None, **context):
    """按通知类型编码发送通知（批量创建 Notification 记录）。

    Args:
        code: 注册表中的通知类型编码。
        target: 动作目标对象（GFK，可为空）。
        action_object: 动作上下文对象（GFK，可为空）。
        actor: 动作发起者（User 或 None；系统通知传 None）。
        **context: 渲染/接收者解析上下文。verb_template 中的占位符需提供字符串键值。

    接收者由注册表的 recipients(context) 解析，默认排除 actor 本人
    （可通过 NotificationType.exclude_actor=False 关闭，用于"审批有你也应收到"的场景）。
    落地页由 url_resolver(target, context) 解析。verb/title/icon/url 创建时快照。
    """
    ntype = get_ntype(code)
    if ntype is None:
        logger.warning("未注册的通知类型: %s", code)
        return

    try:
        verb = ntype.verb_template.format(**context)
    except KeyError as e:
        logger.warning("通知类型 %s 渲染 verb 缺少上下文: %s", code, e)
        verb = ntype.verb_template

    recipients = set(ntype.recipients(context))
    if actor and ntype.exclude_actor:
        recipients.discard(actor)
    if not recipients:
        return

    url = ntype.url_resolver(target, context) if ntype.url_resolver else ''
    title = context.get('title', ntype.label)

    rows = [
        Notification(
            recipient=r, actor=actor, verb=verb, type=code,
            channel=ntype.channel, url=url, title=title, icon=ntype.icon,
            target=target, action_object=action_object,
        )
        for r in recipients
    ]
    Notification.objects.bulk_create(rows)
    logger.debug("Sent %d notifications, type=%s, verb=%s", len(rows), code, verb)


def register_signal_notification(signal, type_code: str, builder, *, sender=None):
    """声明式绑定：某信号触发时，自动按 builder 构造的上下文发送对应类型通知。

    Args:
        signal: 任意 django.dispatch.Signal（含模型信号 post_save 等）。
        type_code: 已注册的通知类型编码。
        builder: (signal_kwargs: dict) -> dict | None。返回 notify() 的
            **context（含 target/action_object/actor 及 verb 占位符）；返回
            None 表示此事件无需通知（用于条件过滤）。
        sender: 可选，仅监听该发送者（如 post_save 限 ProjectNode）。

    在业务 app 的 notifications.py 中调用（ready() 导入触发）。dispatch_uid
    用 type_code 保证幂等，重复导入不重复连接。
    """
    def handler(sender, **kwargs):
        try:
            context = builder(kwargs)
        except Exception:
            logger.exception("通知绑定 %s 的 builder 异常", type_code)
            return
        if context:
            notify(type_code, **context)

    signal.connect(handler, sender=sender, dispatch_uid=f'notif_{type_code}')