from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from app_project.models import ProjectMember
from decimal import Decimal

class UserPerformanceListView(LoginRequiredMixin, View):
    """
    【优化版】全局成员绩效看板视图
    利用 Project.quality_score 冗余字段进行极速统计
    """
    def get(self, request):
        # 1. 核心查询：一次性统计所有用户的得分总和 (利用数据库计算)
        # S_member = Sum(Project.quality_score * Member.workload_share)
        user_stats = User.objects.filter(is_active=True).annotate(
            accumulated_score=Sum(
                ExpressionWrapper(
                    F('projectmember__project__quality_score') * F('projectmember__workload_share'),
                    output_field=DecimalField()
                )
            ),
            project_count=Sum(
                ExpressionWrapper(
                    F('projectmember__id') / F('projectmember__id'), # 巧妙计算计数
                    output_field=DecimalField()
                )
            )
        ).order_by('-accumulated_score')

        # 2. 构造前端数据
        performance_data = []
        for user in user_stats:
            if user.accumulated_score and user.accumulated_score > 0:
                # 获取角色统计 (这部分逻辑较复杂，保持 Python 统计或简单展示)
                memberships = user.projectmember_set.all()
                roles = {'LEAD': 0, 'RND': 0, 'OTHER': 0}
                for m in memberships:
                    if m.role == 'LEAD': roles['LEAD'] += 1
                    elif m.role == 'RND': roles['RND'] += 1
                    else: roles['OTHER'] += 1

                performance_data.append({
                    'user': user,
                    'total_score': user.accumulated_score or Decimal('0.00'),
                    'project_count': memberships.count(),
                    'roles': roles
                })

        context = {
            'performance_data': performance_data,
            'page_title': '成员协同绩效看板'
        }
        return render(request, 'apps/app_project/performance_list.html', context)
