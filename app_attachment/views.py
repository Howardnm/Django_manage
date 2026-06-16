"""
附件 CRUD 视图

提供统一的附件上传、列表、下载、删除功能。
所有视图通过 PermissionAdapter 自动适配各业务模块的权限策略。
"""
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import AttachmentUploadForm
from .models import Attachment
from .registry import get_attachment_config_for_ct
from .utils import PermissionAdapter


# ==========================================
# 基础 Mixin：解析父对象 + 权限检查
# ==========================================
class AttachmentBaseMixin:
    """
    所有附件视图的基础 Mixin。

    负责：
    1. 根据 content_type_id + object_id 解析父对象
    2. 查找附件配置
    3. 构建 PermissionAdapter 并执行权限检查
    """

    def resolve_parent(self, content_type_id, object_id):
        """
        解析父对象。

        Returns:
            (content_type, parent_obj, config)
        """
        ct = get_object_or_404(ContentType, id=content_type_id)
        model_class = ct.model_class()
        if model_class is None:
            raise Http404('模型不存在')
        parent = get_object_or_404(model_class, pk=object_id)
        try:
            config = get_attachment_config_for_ct(ct)
        except ValueError:
            raise Http404('该资源不支持附件功能')
        return ct, parent, config

    def check_permission(self, config, parent_obj, action='view'):
        """调用 PermissionAdapter 执行完整权限校验。"""
        adapter = PermissionAdapter(config)
        adapter.check(self.request, parent_obj, action)


# ==========================================
# 附件列表视图
# ==========================================
class AttachmentListView(AttachmentBaseMixin, View):
    """
    附件列表（HTMX 局部刷新）。

    GET /attachment/<content_type_id>/<object_id>/
    返回文件列表 HTML 片段，支持 HTMX 和普通请求。
    """

    def get(self, request, content_type_id, object_id):
        ct, parent, config = self.resolve_parent(content_type_id, object_id)
        self.check_permission(config, parent, action='view')

        attachments = Attachment.objects.filter(
            content_type=ct,
            object_id=object_id,
            is_deleted=False,
        ).select_related('uploader').order_by('-uploaded_at')

        context = {
            'attachments': attachments,
            'parent': parent,
            'config': config,
            'content_type_id': content_type_id,
            'object_id': object_id,
        }

        # HTMX 请求返回纯内容，普通请求返回完整页面片段
        if request.headers.get('HX-Request'):
            return render(request, 'apps/app_attachment/_file_list.html', context)

        return render(request, 'apps/app_attachment/_attachment_panel.html', context)


# ==========================================
# 附件上传视图
# ==========================================
class AttachmentUploadView(AttachmentBaseMixin, View):
    """
    附件上传（支持 HTMX 弹窗 + 传统表单）。

    GET  /attachment/<ct_id>/<obj_id>/upload/
         → 返回上传表单（HTMX 弹窗内容）

    POST /attachment/<ct_id>/<obj_id>/upload/
         → 处理文件上传
    """

    def get(self, request, content_type_id, object_id):
        ct, parent, config = self.resolve_parent(content_type_id, object_id)
        self.check_permission(config, parent, action='add')

        # 分组选项：如果配置了 group_field，尝试从父对象获取节点列表
        group_choices = None
        if config.group_field:
            group_choices = self._get_group_choices(parent, config)

        # 支持 URL query param 预填 group_key
        initial_group_key = request.GET.get('group_key', '')

        form = AttachmentUploadForm(
            config=config,
            initial={'group_key': initial_group_key},
        )

        # 查找 group_key 对应的显示标签
        group_label = ''
        if initial_group_key and group_choices:
            for key, label in group_choices:
                if key == initial_group_key:
                    group_label = label
                    break

        return render(request, 'apps/app_attachment/_upload_modal.html', {
            'form': form,
            'parent': parent,
            'config': config,
            'content_type_id': content_type_id,
            'object_id': object_id,
            'group_label': group_label,
        })

    def _get_group_choices(self, parent, config):
        """通过 config.group_choices_resolver 获取分组选项"""
        choices = [('', '通用资料（不关联节点）')]
        if config.group_choices_resolver:
            try:
                extra = config.group_choices_resolver(parent)
                if extra:
                    choices.extend(extra)
            except Exception:
                pass
        return choices

    def post(self, request, content_type_id, object_id):
        ct, parent, config = self.resolve_parent(content_type_id, object_id)
        self.check_permission(config, parent, action='add')

        # 检查附件数量限制
        if config.max_attachments is not None:
            current_count = Attachment.objects.filter(
                content_type=ct,
                object_id=object_id,
                is_deleted=False,
            ).count()
            if current_count >= config.max_attachments:
                messages.error(
                    request,
                    f'附件数量已达上限（{config.max_attachments}个），请删除旧文件后再上传。'
                )
                if request.headers.get('HX-Request'):
                    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
                return redirect(request.META.get('HTTP_REFERER', '/'))

        form = AttachmentUploadForm(request.POST, request.FILES, config=config)

        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.content_type = ct
            attachment.object_id = object_id
            attachment.uploader = request.user
            attachment.save()

            messages.success(request, f'文件 "{attachment.display_name}" 上传成功')
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
            return redirect(request.META.get('HTTP_REFERER', '/'))

        # 表单验证失败
        messages.error(request, '上传失败，请检查文件格式和大小（最大50MB）')
        if request.headers.get('HX-Request'):
            # 重新获取 group_label（与 GET 逻辑一致）
            group_label = ''
            group_key_val = request.POST.get('group_key', '')
            if group_key_val and config.group_field:
                choices = self._get_group_choices(parent, config)
                for key, label in choices:
                    if key == group_key_val:
                        group_label = label
                        break
            return render(request, 'apps/app_attachment/_upload_modal.html', {
                'form': form,
                'parent': parent,
                'config': config,
                'content_type_id': content_type_id,
                'object_id': object_id,
                'group_label': group_label,
            }, status=422)

        return redirect(request.META.get('HTTP_REFERER', '/'))


# ==========================================
# 附件下载视图
# ==========================================
class AttachmentDownloadView(AttachmentBaseMixin, View):
    """
    安全文件下载。

    GET /attachment/download/<token>/
    UUID token 防枚举：无效 token 统一返回 403。
    """

    def get(self, request, token):
        # 校验 token 格式，无效格式直接 403
        import uuid as _uuid
        try:
            _uuid.UUID(token)
        except (ValueError, AttributeError):
            raise PermissionDenied

        attachment = (
            Attachment.objects
            .select_related('content_type')
            .filter(download_token=token, is_deleted=False)
            .first()
        )
        if attachment is None:
            raise PermissionDenied

        ct = attachment.content_type
        try:
            config = get_attachment_config_for_ct(ct)
        except ValueError:
            raise PermissionDenied

        # 解析父对象用于权限检查
        model_class = ct.model_class()
        if model_class is None:
            raise PermissionDenied
        parent = model_class.objects.filter(pk=attachment.object_id).first()
        if parent is None:
            raise PermissionDenied
        self.check_permission(config, parent, action='view')

        if not attachment.file:
            raise PermissionDenied

        try:
            return FileResponse(
                attachment.file.open('rb'),
                as_attachment=False,
            )
        except FileNotFoundError:
            raise PermissionDenied


# ==========================================
# 附件删除视图
# ==========================================
class AttachmentDeleteView(AttachmentBaseMixin, View):
    """
    附件删除（软删除）。

    POST /attachment/delete/<pk>/
    """

    def post(self, request, pk):
        attachment = get_object_or_404(
            Attachment.objects.select_related('content_type'),
            pk=pk,
            is_deleted=False,
        )

        ct = attachment.content_type
        config = get_attachment_config_for_ct(ct)

        # 解析父对象用于权限检查
        model_class = ct.model_class()
        if model_class is None:
            raise Http404('模型不存在')
        parent = get_object_or_404(model_class, pk=attachment.object_id)
        self.check_permission(config, parent, action='delete')

        # 软删除
        attachment.is_deleted = True
        attachment.save(update_fields=['is_deleted'])

        messages.success(request, f'文件 "{attachment.display_name}" 已删除')

        if request.headers.get('HX-Request'):
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return redirect(request.META.get('HTTP_REFERER', '/'))
