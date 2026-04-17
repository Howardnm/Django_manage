from django.shortcuts import render
from django.views import View
from app_basic_research.mixins import BasicResearchAccessMixin


class BasicResearchOverviewView(BasicResearchAccessMixin, View):
    """
    预研项目看板：
    - 准入：需有 app_basic_research.view_researchproject 权限。
    - 隔离：继承预研模块的纯研发部门隔离逻辑。
    """
    permission_required = 'app_basic_research.view_researchproject'
    template_name = 'apps/app_panel/basic_research_overview.html'

    def get(self, request):
        context = {
            'page_title': '基础预研看板'
        }
        return render(request, self.template_name, context)
