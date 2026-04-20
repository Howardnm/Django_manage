from django.db.models import Count
from django.views.generic import ListView
from app_repository.models import ExternalMemberActivity, Customer, OEM
from app_panel.mixins import PanelAccessMixin

class CustomerActivityOverviewView(PanelAccessMixin, ListView):
    """
    客户行为全览看板：
    - 准入：内部全员 (INTERNAL_STAFF)。
    - 功能：展示外部会员在电子手册上的实时轨迹和热点分析。
    """
    model = ExternalMemberActivity
    template_name = 'apps/app_panel/customer_activity.html'
    context_object_name = 'activities'
    paginate_by = 50
    
    # 看板全局可见，便于销售和研发同步市场需求
    enforce_dept_isolation = False

    def get_queryset(self):
        return ExternalMemberActivity.objects.all().order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 1. 热门关注牌号 TOP 10
        hot_materials = ExternalMemberActivity.objects.values('target_name').annotate(
            total_count=Count('id')
        ).order_by('-total_count')[:10]
        
        # 2. 热门下载行为统计
        hot_downloads = ExternalMemberActivity.objects.filter(action__icontains='DOWNLOAD').values('target_name').annotate(
            download_count=Count('id')
        ).order_by('-download_count')[:10]

        # 3. 统计各角色活跃度
        role_distribution = {
            'VIEW': ExternalMemberActivity.objects.filter(action='VIEW').count(),
            'DOWNLOAD': ExternalMemberActivity.objects.filter(action__icontains='DOWNLOAD').count(),
        }

        context.update({
            'page_title': '外部客户行为全览',
            'hot_materials': hot_materials,
            'hot_downloads': hot_downloads,
            'role_distribution': role_distribution,
        })
        return context
