"""
附件模块 URL 路由

提供 RESTful 风格的附件 CRUD 端点。
"""
from django.urls import path

from .views import (
    AttachmentListView,
    AttachmentUploadView,
    AttachmentDownloadView,
    AttachmentViewerView,
    AttachmentDeleteView,
)

app_name = 'attachment'

urlpatterns = [
    # GET /attachment/<content_type_id>/<object_id>/
    # 附件列表（HTMX 局部刷新）
    path(
        '<int:content_type_id>/<int:object_id>/',
        AttachmentListView.as_view(),
        name='list',
    ),

    # GET|POST /attachment/<content_type_id>/<object_id>/upload/
    # GET → 上传表单  |  POST → 处理上传
    path(
        '<int:content_type_id>/<int:object_id>/upload/',
        AttachmentUploadView.as_view(),
        name='upload',
    ),

    # GET /attachment/download/<token>/
    # 安全文件下载（UUID token 防枚举）
    path(
        'download/<str:token>/',
        AttachmentDownloadView.as_view(),
        name='download',
    ),

    # GET /attachment/viewer/<token>/
    # 通用在线预览分发（按 preview_kind 选模板，当前仅 cad3d）
    path(
        'viewer/<str:token>/',
        AttachmentViewerView.as_view(),
        name='viewer',
    ),

    # POST /attachment/delete/<pk>/
    # 软删除附件
    path(
        'delete/<int:pk>/',
        AttachmentDeleteView.as_view(),
        name='delete',
    ),
]
