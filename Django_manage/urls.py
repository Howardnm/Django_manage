"""
URL configuration for Django_manage project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render # 导入 render
from common_utils.SecureFileDownload import SecureFileDownloadView
from debug_toolbar.toolbar import debug_toolbar_urls # 这是debug_toolbar的配置


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
    path('project/', include('app_project.urls')),
    path('research/', include('app_basic_research.urls')),
    path('user/', include('app_user.urls')),
    path('repository/', include('app_repository.urls')),
    path('raw-material/', include('app_raw_material.urls')),
    path('process/', include('app_process.urls')),
    path('formula/', include('app_formula.urls')),
    # 通用下载路由
    path('download/<str:app_label>/<str:model_name>/<int:pk>/<str:field_name>/', SecureFileDownloadView.as_view(), name='secure_download'),
    # 添加无权限页面的 URL 模式
    path('permission-denied/', permission_denied_view, name='permission_denied'),
] + debug_toolbar_urls() # 这是debug_toolbar的配置
