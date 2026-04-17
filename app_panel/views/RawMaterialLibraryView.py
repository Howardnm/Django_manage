from django.shortcuts import render
from django.views import View
from app_raw_material.mixins import RawMaterialAccessMixin

class RawMaterialLibraryView(RawMaterialAccessMixin, View):
    """
    原材料库看板：
    - 准入：需有 app_raw_material.view_rawmaterial 权限。
    - 隔离：内部全员共享。
    """
    permission_required = 'app_raw_material.view_rawmaterial'

    def get(self, request):
        return render(request, 'apps/app_panel/raw_material_library.html')
