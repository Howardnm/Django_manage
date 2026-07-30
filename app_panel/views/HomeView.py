from django.shortcuts import render
from django.views import View

from app_panel.mixins import PanelAccessMixin


class HomeView(PanelAccessMixin, View):
    """系统首页：纯静态系统介绍页，登录后的安全兜底。

    L1/L2: PanelAccessMixin (module_code='panel') 从 DB 读取。
    L3: 显式声明 [] — 本页为零数据库查询的纯静态页面，无适用 L3 权限码。
    """

    permission_required = []  # 纯静态页面，零数据查询

    def get(self, request):
        return render(request, 'apps/app_panel/home.html')
