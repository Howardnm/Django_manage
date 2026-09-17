"""
附件模块模板标签

提供一行代码嵌入完整附件面板的能力：
    {% load attachment_tags %}
    {% attachment_panel parent_obj %}

以及按分类取附件下载链接（列表页需配合 attachment_prime 使用）：
    {% attachment_prime materials %}
    {% attachment_url material 'TDS' as tds_url %}
"""
from django import template
from django.contrib.contenttypes.models import ContentType

from app_attachment.registry import get_attachment_config_for_model
from app_attachment.utils import attachment_tokens_for, prime_attachment_tokens

register = template.Library()


@register.inclusion_tag('apps/app_attachment/_attachment_panel.html', takes_context=True)
def attachment_panel(context, parent_obj):
    """
    渲染完整的附件面板（文件列表 + 上传按钮 + 上传弹窗）。

    Usage:
        {% load attachment_tags %}
        {% attachment_panel project %}
        {% attachment_panel material %}

    不查附件表：面板里的文件列表由 HTMX (`attachment:list`) 异步填充，
    头部数量徽标也由该响应通过 hx-swap-oob 回填 —— 在此处统计只会多打一次
    COUNT，而列表加载完就不再准确。
    """
    ct = ContentType.objects.get_for_model(parent_obj)
    config = get_attachment_config_for_model(type(parent_obj))

    return {
        'parent': parent_obj,
        'config': config,
        'content_type_id': ct.id,
        'object_id': parent_obj.pk,
        'request': context.get('request'),
    }


@register.simple_tag
def attachment_prime(objects):
    """
    行循环前调用一次：把这批父对象的附件映射一次查完。

    Usage:
        {% load attachment_tags %}
        {% attachment_prime materials %}
        {% for m in materials %}
            {% attachment_url m 'TDS' as tds_url %}
        {% endfor %}

    不做这一步的话，循环里每个对象各查一次库（每页行数 = 每页查询数）。
    单个对象的详情页不需要它 —— 三件套自己会共用一次装载。
    """
    prime_attachment_tokens(objects)
    return ''


@register.simple_tag
def attachment_url(parent_obj, category):
    """
    获取指定分类的最新附件的下载 URL。

    Usage:
        {% load attachment_tags %}
        {% attachment_url material 'TDS' as tds_url %}
        {% if tds_url %}<a href="{{ tds_url }}">TDS</a>{% endif %}

    三件套（TDS / MSDS / RoHS）是同一次渲染里对同一父对象的连续调用，
    因此把整个分类→token 映射缓存在父对象实例上，三次调用只查一次库。
    列表页请在行循环前先用 attachment_prime 批量预载，否则每行仍各查一次。

    装载规则见 app_attachment/utils.py（单条与批量共用同一份挂载点）。
    """
    from django.urls import reverse

    token = attachment_tokens_for(parent_obj).get(category)
    if not token:
        return ''
    return reverse('attachment:download', kwargs={'token': token})


@register.inclusion_tag('apps/app_attachment/_upload_modal.html', takes_context=True)
def attachment_upload_modal(context, parent_obj):
    """
    只渲染上传弹窗（用于页面底部集中放置弹窗 HTML）。

    Usage:
        {% load attachment_tags %}
        {% attachment_upload_modal project %}
    """
    from app_attachment.forms import AttachmentUploadForm
    ct = ContentType.objects.get_for_model(parent_obj)
    config = get_attachment_config_for_model(type(parent_obj))

    return {
        'form': AttachmentUploadForm(config=config),
        'parent': parent_obj,
        'config': config,
        'content_type_id': ct.id,
        'object_id': parent_obj.pk,
        'request': context.get('request'),
    }
