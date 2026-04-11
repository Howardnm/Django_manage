"""
URL configuration for Django_manage project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from common_utils.SecureFileDownload import SecureFileDownloadView
from debug_toolbar.toolbar import debug_toolbar_urls

# 自定义 Admin 站点标题
admin.site.site_header = "项目管理系统后台"
admin.site.site_title = "项目管理系统"
admin.site.index_title = "欢迎使用项目管理系统"

# 定义一个简单的视图函数来渲染无权限页面
def permission_denied_view(request):
    return render(request, 'permission_denied.html', status=403)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app_panel.urls')),
    path('catalog/', include('app_catalog.urls')), 
    path('project/', include('app_project.urls')),
    path('research/', include('app_basic_research.urls')),
    path('user/', include('app_user.urls')),
    path('repository/', include('app_repository.urls')),
    path('material/', include('app_material.urls')),
    path('raw-material/', include('app_raw_material.urls')),
    path('process/', include('app_process.urls')),
    path('formula/', include('app_formula.urls')),
    path('notifications/', include('app_notification.urls')),
    path('dify-sync/', include('app_dify_sync.urls')),
    
    # API 接口 (Material Core)
    path('api/material/', include('app_material.api.urls')),

    # MCP Server HTTP/SSE 接口
    path('mcp/', include('app_mcp_server.urls')),

    # 通用下载路由
    path('download/<str:app_label>/<str:model_name>/<int:pk>/<str:field_name>/', SecureFileDownloadView.as_view(), name='secure_download'),
    path('permission-denied/', permission_denied_view, name='permission_denied'),
] + debug_toolbar_urls()
