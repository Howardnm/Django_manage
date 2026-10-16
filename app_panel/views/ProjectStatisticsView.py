from django.http import JsonResponse
from django.db.models import Count, Subquery, OuterRef, Exists, Case, When, Value, CharField
from django.shortcuts import render
from django.views import View
from app_panel.mixins import PanelAccessMixin
from app_panel.utils.filters import ProjectStatisticsFilter
from app_project.models import Project, ProjectStage, ProjectNode

# 柱图顺序，与 project_statistics.html 的 categories 一致
STAT_KEYS = (
    'in_development',
    're_development',
    'developed_not_sampled',
    'first_sample_delivery',
    'multiple_sample_deliveries',
    'qualified_awaiting_production',
    'mid_test_completed',
    'mass_production_completed',
    'paused',
    'terminated',
)
ANALYSIS_KEYS = (
    'pass_rate',
    'mass_prod_rate',
    'feedback_rate',
    'pause_rate',
    'termination_rate',
)
# 未开始或正在办（含待审批）。待审批以前被漏出全部分桶。
_OPEN = ('PENDING', 'DOING', 'AWAITING_APPROVAL')
# 正在办，不含「未开始」。一次/多次送样用这个，未开始的小试归「已开发未送样」。
_IN_PROGRESS = ('DOING', 'AWAITING_APPROVAL')


def _pct(numerator, denominator):
    """比率保留两位小数。分母为 0 时返回 0.0。"""
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 2)


def _empty_stats():
    return {key: 0 for key in STAT_KEYS}


def _empty_analysis():
    return {key: 0.0 for key in ANALYSIS_KEYS}


class ProjectStatisticsView(PanelAccessMixin, View):
    """
    项目统计看板：
    - 逻辑：基于节点状态、轮次及异常历史进行 10 维度分类统计。
    - 一个项目只落入一个桶，优先级见 _bucket_case。
    """
    permission_required = 'app_project.view_project'

    def get(self, request):
        base_qs = Project.objects.all().select_related('manager', 'manager__department')
        filter_set = ProjectStatisticsFilter(request.GET, queryset=base_qs)
        projects_qs = filter_set.qs

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return self._get_json_stats(projects_qs)

        context = {
            'filter': filter_set,
            'page_title': '项目统计看板',
        }
        return render(request, 'apps/app_panel/project_statistics.html', context)

    def _get_json_stats(self, projects_qs):
        total_projects = projects_qs.count()

        if total_projects == 0:
            return JsonResponse({
                'total_projects': 0,
                'stats': _empty_stats(),
                'analysis': _empty_analysis(),
            })

        annotated_qs = projects_qs.annotate(
            has_failed_pilot=Exists(
                ProjectNode.objects.filter(project=OuterRef('pk'), stage=ProjectStage.PILOT, status='FAILED')
            ),
            has_paused_node=Exists(
                ProjectNode.objects.filter(project=OuterRef('pk'), status='PAUSED')
            ),
            last_rnd_status=_last_status(ProjectStage.RND),
            last_pilot_status=_last_status(ProjectStage.PILOT),
            last_mid_test_status=_last_status(ProjectStage.MID_TEST),
            last_mass_prod_status=_last_status(ProjectStage.MASS_PROD),
        ).annotate(bucket=_bucket_case())
        counted = annotated_qs.values('bucket').annotate(n=Count('id'))
        counts = {row['bucket']: row['n'] for row in counted}
        stats = {key: counts.get(key, 0) for key in STAT_KEYS}

        total_for_rates = total_projects - stats['terminated']
        qualified_like = (
            stats['mass_production_completed']
            + stats['mid_test_completed']
            + stats['qualified_awaiting_production']
        )
        analysis = {
            # 项目合格率 = (已量产 + 已中试 + 合格待产) / (总项目数 - 终止项目数)
            'pass_rate': _pct(qualified_like, total_for_rates),
            # 项目量产率 = 已量产 / (总项目数 - 终止项目数)
            'mass_prod_rate': _pct(stats['mass_production_completed'], total_for_rates),
            # 项目反馈率 = 至少拥有一个 FEEDBACK 阶段节点的项目占比
            'feedback_rate': _pct(
                projects_qs.filter(nodes__stage=ProjectStage.FEEDBACK).distinct().count(),
                total_projects,
            ),
            'pause_rate': _pct(stats['paused'], total_projects),
            'termination_rate': _pct(stats['terminated'], total_projects),
        }

        return JsonResponse({
            'total_projects': total_projects,
            'stats': stats,
            'analysis': analysis,
        })


def _last_status(stage):
    return Subquery(
        ProjectNode.objects.filter(project=OuterRef('pk'), stage=stage)
        .order_by('-order')
        .values('status')[:1]
    )


def _bucket_case():
    """优先级从高到低，先命中的桶独占该项目。

    终止 → 暂停 → 已量产 → 已中试 → 合格待产 → 多次送样 → 一次送样
    → 已开发未送样 → 不合格再开发 → 开发中。
    """
    return Case(
        When(is_terminated=True, then=Value('terminated')),
        When(has_paused_node=True, then=Value('paused')),
        # 已量产：最后一轮客户量产下单已完成
        When(last_mass_prod_status='DONE', then=Value('mass_production_completed')),
        # 已中试：中试已完成，量产下单尚未开始或正在进行（含待审批）
        When(
            last_mid_test_status='DONE',
            last_mass_prod_status__in=_OPEN,
            then=Value('mid_test_completed'),
        ),
        # 合格待产：小试已完成，中试尚未开始或正在进行
        When(
            last_pilot_status='DONE',
            last_mid_test_status__in=_OPEN,
            then=Value('qualified_awaiting_production'),
        ),
        # 多次送样：有过小试失败，研发已完成，最后一轮小试正在进行
        When(
            has_failed_pilot=True,
            last_rnd_status='DONE',
            last_pilot_status__in=_IN_PROGRESS,
            then=Value('multiple_sample_deliveries'),
        ),
        # 一次送样：从未小试失败，研发已完成，小试正在进行
        When(
            has_failed_pilot=False,
            last_rnd_status='DONE',
            last_pilot_status__in=_IN_PROGRESS,
            then=Value('first_sample_delivery'),
        ),
        # 已开发未送样：研发已完成，小试仍未开始
        When(
            last_rnd_status='DONE',
            last_pilot_status='PENDING',
            then=Value('developed_not_sampled'),
        ),
        # 不合格再开发：有过小试失败，最后一轮研发未开始或正在进行
        When(
            has_failed_pilot=True,
            last_rnd_status__in=_OPEN,
            then=Value('re_development'),
        ),
        # 开发中：从未小试失败，最后一轮研发未开始或正在进行
        When(
            has_failed_pilot=False,
            last_rnd_status__in=_OPEN,
            then=Value('in_development'),
        ),
        default=Value(''),
        output_field=CharField(),
    )
