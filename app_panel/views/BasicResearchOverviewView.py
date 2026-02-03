from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View
from app_panel.mixins import CustomPermissionRequiredMixin

class BasicResearchOverviewView(LoginRequiredMixin, CustomPermissionRequiredMixin, View):
    """
    基础预研项目看板视图
    """
    permission_required = 'app_basic_research.view_researchproject'
    template_name = 'apps/app_panel/basic_research_overview.html'

    def get(self, request):
        context = {
            'page_title': '基础预研看板'
        }
        return render(request, self.template_name, context)
