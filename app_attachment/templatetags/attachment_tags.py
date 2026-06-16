"""
附件模块模板标签

提供一行代码嵌入完整附件面板的能力：
    {% load attachment_tags %}
    {% attachment_panel parent_obj %}
"""
from django import template
from django.contrib.contenttypes.models import ContentType

from app_attachment.models import Attachment
from app_attachment.registry import get_attachment_config_for_model

register = template.Library()


@register.inclusion_tag('apps/app_attachment/_attachment_panel.html', takes_context=True)
def attachment_panel(context, parent_obj):
    """
    渲染完整的附件面板（文件列表 + 上传按钮 + 上传弹窗）。

    Usage:
        {% load attachment_tags %}
        {% attachment_panel project %}
        {% attachment_panel material %}
    """
    ct = ContentType.objects.get_for_model(parent_obj)
    config = get_attachment_config_for_model(type(parent_obj))

    attachments = Attachment.objects.filter(
        content_type=ct,
        object_id=parent_obj.pk,
        is_deleted=False,
    ).select_related('uploader').order_by('-uploaded_at')

    return {
        'attachments': attachments,
        'parent': parent_obj,
        'config': config,
        'content_type_id': ct.id,
        'object_id': parent_obj.pk,
        'request': context.get('request'),
    }


@register.simple_tag
def attachment_url(parent_obj, category):
    """
    获取指定分类的第一个附件的下载 URL。

    Usage:
        {% load attachment_tags %}
        {% attachment_url material 'TDS' as tds_url %}
        {% if tds_url %}<a href="{{ tds_url }}">TDS</a>{% endif %}
    """
    from django.urls import reverse
    ct = ContentType.objects.get_for_model(parent_obj)
    att = Attachment.objects.filter(
        content_type=ct, object_id=parent_obj.pk,
        category=category, is_deleted=False,
    ).first()
    if att and att.pk:
        return reverse('attachment:download', kwargs={'token': att.download_token})
    return ''


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
