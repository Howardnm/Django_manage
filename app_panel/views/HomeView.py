from django.shortcuts import render
from django.views import View

from app_panel.mixins import HomeAccessMixin, PanelAccessMixin


class HomeView(HomeAccessMixin, View):
    """系统首页：纯静态系统介绍页，登录后的安全兜底。

    L1/L2: HomeAccessMixin (module_code='home') 从 DB 读取 — 与看板（panel）权限解耦。
    L3: 显式声明 [] — 本页为零数据库查询的纯静态页面，无适用 L3 权限码。
    """

    permission_required = []  # 纯静态页面，零数据查询

    def get(self, request):
        context = {
            # 供模板控制"进入个人工作台"按钮可见性（仅 panel 权限用户可见）
            'has_panel_access': PanelAccessMixin.user_has_access(request.user),
        }
        return render(request, 'apps/app_panel/home.html', context)
