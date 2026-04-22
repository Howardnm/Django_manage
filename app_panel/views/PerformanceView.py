from django.shortcuts import render
from django.views import View
from django.contrib.auth import get_user_model
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from app_panel.mixins import PanelAccessMixin
from decimal import Decimal

User = get_user_model()

class UserPerformanceListView(PanelAccessMixin, View):
    """
    【双分制版】全局成员绩效看板视图：
    1. 有效贡献得分：考虑项目等级加权 SUM((得分 * 占比 / 100) * 因子)
    2. 基础工作量得分：仅看产出质量与占比 SUM(得分 * 占比 / 100)
    """
    def get(self, request):
        # 核心加权得分计算逻辑
        user_stats = User.objects.filter(is_active=True).annotate(
            # 1. 有效贡献得分 (带等级加权)
            effective_contribution_score=Coalesce(
                Sum(
                    ExpressionWrapper(
                        (F('projectmember__project__quality_score') * F('projectmember__workload_share') / 100.0) * 
                        Coalesce(F('projectmember__project__grade__factor'), 1.0, output_field=DecimalField()),
                        output_field=DecimalField()
                    )
                ),
                0.00,
                output_field=DecimalField()
            ),
            # 2. 基础工作量得分 (不带等级加权)
            base_workload_score=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F('projectmember__project__quality_score') * F('projectmember__workload_share') / 100.0,
                        output_field=DecimalField()
                    )
                ),
                0.00,
                output_field=DecimalField()
            )
        ).order_by('-effective_contribution_score')

        # 2. 构造前端数据
        performance_data = []
        for user in user_stats:
            # 只要有任何得分就展示
            if user.effective_contribution_score > 0 or user.base_workload_score > 0:
                memberships = user.projectmember_set.all()
                roles = {'LEAD': 0, 'RND': 0, 'OTHER': 0}
                for m in memberships:
                    if m.role == 'LEAD': roles['LEAD'] += 1
                    elif m.role == 'RND': roles['RND'] += 1
                    else: roles['OTHER'] += 1

                performance_data.append({
                    'user': user,
                    'effective_score': user.effective_contribution_score,
                    'workload_score': user.base_workload_score,
                    'project_count': memberships.count(),
                    'roles': roles
                })

        context = {
            'performance_data': performance_data,
            'page_title': '成员协同绩效看板'
        }
        return render(request, 'apps/app_project/performance_list.html', context)
