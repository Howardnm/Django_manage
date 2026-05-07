"""
URL configuration for Django_manage project.
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

def permission_denied_view(request):
    return render(request, 'permission_denied.html', status=403)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app_panel.urls')),
    path('catalog/', include('app_catalog.urls')), 
    path('project/', include('app_project.urls')),
    path('workflow/', include('app_workflow.urls')), # 【新增】工作流中心
    path('research/', include('app_basic_research.urls')),
    path('user/', include('app_user.urls')),
    path('repository/', include('app_repository.urls')),
    path('material/', include('app_material.urls')),
    path('raw-material/', include('app_raw_material.urls')),
    path('process/', include('app_process.urls')),
    path('formula/', include('app_formula.urls')),
    path('forms/', include('app_form_management.urls')),
    path('notifications/', include('app_notification.urls')),
    
    # 核心 API 重构：由 app_material_api 管控
    path('api/material/', include('app_material_api.urls')),

    # MCP Server 接口
    path('mcp/', include('app_mcp_server.urls')),
    
    # 【修复】：重新挂载 Dify 同步与机器人路由
    path('dify/', include('app_dify_sync.urls')),

    # 通用下载路由
    path('download/<str:app_label>/<str:model_name>/<int:pk>/<str:field_name>/', SecureFileDownloadView.as_view(), name='secure_download'),
    path('permission-denied/', permission_denied_view, name='permission_denied'),
] + debug_toolbar_urls()
