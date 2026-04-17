from django.shortcuts import render
from django.views import View
from app_material.mixins import MaterialAccessMixin

class MaterialLibraryView(MaterialAccessMixin, View):
    """
    成品材料库看板：
    - 准入：需有 app_material.view_materiallibrary 权限。
    - 隔离：全员内部可见。
    """
    permission_required = 'app_material.view_materiallibrary'

    def get(self, request):
        return render(request, 'apps/app_panel/material_library.html')
