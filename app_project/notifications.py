"""
app_project 通知接入 — 项目节点更新通知的类型定义 + 声明式信号绑定。

定义 project.node_updated 类型，并把 ProjectNode 的 post_save(更新时) 信号
声明式绑定到它。在 AppConfig.ready() 中 import 本模块即完成注册与接线。
"""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

from app_notification.registry import NotificationType, register_ntype
from app_notification.services import register_signal_notification
from app_notification.thread_local import get_current_user

User = get_user_model()


def _project_node_recipients(context: dict):
    """项目节点更新 → 项目负责人 + 项目成员。"""
    node = context['node']
    project = node.project
    user_ids = {project.manager_id} if project.manager_id else set()
    user_ids.update(
        project.members.select_related('user').values_list('user_id', flat=True)
    )
    return User.objects.filter(pk__in=user_ids)


def _content_url(target, context: dict) -> str:
    """委托 RelatedObjectRouter 解析业务对象落地页。"""
    from app_workflow.utils import related_object_router
    return related_object_router.resolve(target) or ''


def _register_project_types() -> None:
    register_ntype(NotificationType(
        code='project.node_updated',
        label='项目节点更新',
        verb_template='更新了进度节点「{stage}」',
        recipients=_project_node_recipients,
        url_resolver=_content_url,
        icon='ti-folder',
    ))


def _node_updated_builder(kw: dict):
    """post_save 仅在更新时通知（created=False），actor 取 thread_local 当前用户。"""
    if kw.get('created'):
        return None
    node = kw['instance']
    return {
        'target': node,
        'action_object': node.project,
        'actor': get_current_user(),
        'node': node,
        'stage': node.get_stage_display() if hasattr(node, 'get_stage_display') else '',
    }


def _register_project_bindings() -> None:
    register_signal_notification(
        post_save, 'project.node_updated', _node_updated_builder,
        sender='app_project.ProjectNode',
    )


# import 本模块即完成注册与接线（AppConfig.ready() 触发）
_register_project_types()
_register_project_bindings()