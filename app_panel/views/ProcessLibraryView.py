from django.shortcuts import render
from django.views import View
from app_process.mixins import ProcessAccessMixin

class ProcessLibraryView(ProcessAccessMixin, View):
    """
    工艺库看板：
    - 准入：需有 app_process.view_processprofile 权限。
    - 隔离：技术核心 (研发+工艺)。
    """
    permission_required = 'app_process.view_processprofile'

    def get(self, request):
        return render(request, 'apps/app_panel/process_library.html')
