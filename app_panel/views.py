# apps/app_panel/views.py
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q, Max

from app_project.models import Project, ProjectNode, ProjectStage
# 引入之前写好的权限 Mixin (确保路径正确)
from app_project.mixins import ProjectPermissionMixin


class PanelIndexView(LoginRequiredMixin, ProjectPermissionMixin, View):
    def get(self, request):
        # 1. 获取项目 (复用 Mixin)
        # 【优化】显式加上 .order_by('-created_at')，确保绝对是按时间倒序（虽然models已经设置了class Meta）
        base_qs = Project.objects.prefetch_related('nodes', 'manager', 'manager__groups').order_by('-created_at')
        projects = self.get_permitted_queryset(base_qs)

        now = timezone.now()
        # 2. 初始化统计容器 (保持不变)
        stats = {
            'total_all': 0,  # 总数
            'total_active': 0,  # 进行中
            'total_completed': 0,  # 【新增】已完成
            'total_terminated': 0,  # 【新增】已终止
            'total_users': set(),
            'stage_counts': {},
            'stagnant_14d': [],
            'stagnant_30d': [],
            'multi_round_pilot': [],
            'member_stats': {},
            'group_stats': {},  # 【新增】用于存各组数据
        }
        for code, label in ProjectStage.choices:
            if code != 'FEEDBACK':  # 排除：客户意见
                stats['stage_counts'][label] = 0  # 将每个阶段的项目数量初始化为0

        # 3. 核心遍历 (大幅简化)
        for project in projects:
            # 【核心修改】直接调用 app_project Model 方法
            info = project.get_progress_info()
            stats['total_all'] += 1

            # 【修正点 1】先提取变量，方便后续多次使用，代码更清晰
            is_terminated = info['is_terminated']
            is_completed = (info['percent'] == 100)

            # A. 全局统计
            if is_terminated:
                stats['total_terminated'] += 1
                # 注意：这里不能 continue！如果 continue 了，后面的分组统计代码就执行不到了。
                # 已终止的项目也要算在“分组统计”里。
            elif is_completed:
                stats['total_completed'] += 1
                # 同理，不要 continue
            else:
                stats['total_active'] += 1

            stats['total_users'].add(project.manager.id)

            # 【修正点 2】节点统计 (仅针对活跃项目)
            # 只有没终止、没完成的项目，才需要去统计停滞和多轮小试
            if not is_terminated and not is_completed:
                # 【核心修改】直接获取当前节点对象
                current_node = info['current_node_obj']
                if current_node:
                    # B. 统计各阶段数量
                    stage_label = current_node.get_stage_display()
                    if stage_label in stats['stage_counts']:
                        stats['stage_counts'][stage_label] += 1

                    # C. 统计停滞
                    if current_node.status in ['PENDING', 'DOING']:
                        days_diff = (now - current_node.updated_at).days
                        if days_diff >= 30:
                            stats['stagnant_30d'].append({'p': project, 'days': days_diff, 'node': current_node})
                        elif days_diff >= 14:
                            stats['stagnant_14d'].append({'p': project, 'days': days_diff, 'node': current_node})

                    # D. 统计多轮
                    if current_node.stage in ['RND', 'PILOT'] and current_node.round > 1:
                        stats['multi_round_pilot'].append({'p': project, 'round': current_node.round})

            # E. 统计成员负载 (所有项目都算，还是只算活跃？通常算活跃的，这里假设算活跃的)
            if not is_terminated and not is_completed:
                uid = project.manager.id
                if uid not in stats['member_stats']:
                    stats['member_stats'][uid] = {
                        'name': project.manager.username,
                        'avatar': project.manager.username[0].upper(),
                        'project_count': 0,
                        'projects': []
                    }
                stats['member_stats'][uid]['project_count'] += 1
                if len(stats['member_stats'][uid]['projects']) < 3:
                    stats['member_stats'][uid]['projects'].append(project.name)

            # F. 统计各组项目情况 (所有项目都统计)
            # 这里必须放在最外面，不能被 continue 跳过
            groups = project.manager.groups.all()  # 因为加了 prefetch，这里极快
            group_names = [g.name for g in groups] if groups else ['未分组']

            for g_name in group_names:
                if g_name not in stats['group_stats']:
                    stats['group_stats'][g_name] = {
                        'total': 0, 'active': 0, 'completed': 0, 'terminated': 0
                    }

                s = stats['group_stats'][g_name]
                s['total'] += 1

                if is_terminated:
                    s['terminated'] += 1
                elif is_completed:
                    s['completed'] += 1
                else:
                    s['active'] += 1

        context = {
            'stats': stats,
            'user_count': len(stats['total_users']),
            'member_stats_list': sorted(stats['member_stats'].values(), key=lambda x: x['project_count'], reverse=True)
        }
        return render(request, 'apps/app_panel/index.html', context)
