from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

class ProcessLibraryView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_process.view_processprofile' # 修改为 app_process 的权限
    raise_exception = True

    def get(self, request):
        return render(request, 'apps/app_panel/process_library.html')
