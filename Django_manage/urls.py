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

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app_panel.urls')),
    path('project/', include('app_project.urls')),
    path('user/', include('app_user.urls')),
    path('repository/', include('app_repository.urls')),
    path('raw-material/', include('app_raw_material.urls')),
    path('process/', include('app_process.urls')),
    # 【新增】配方数据库路由
    path('formula/', include('app_formula.urls')),
]
