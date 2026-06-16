from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView, DetailView
from django.http import HttpResponse

from app_basic_research.forms import ResearchProjectForm, ResearchProjectNodeUpdateForm
from app_basic_research.models import ResearchProject, ResearchStage, ResearchProjectNode
from app_basic_research.utils.filters import ResearchProjectFilter
from app_basic_research.mixins import BasicResearchAccessMixin


# ==========================================
# 1. 预研项目列表
# ==========================================
class ResearchProjectListView(BasicResearchAccessMixin, View):
    """预研列表：仅限研发及管理员，严格部门隔离"""
    permission_required = 'app_basic_research.view_researchproject'
    model = ResearchProject # 必须显式声明模型，供 Mixin 自动执行 get_queryset

    def get(self, request):
        # 自动探测 'manager' 并执行过滤
        base_qs = self.get_queryset().select_related('manager').order_by('-created_at')

        filter_set = ResearchProjectFilter(request.GET, queryset=base_qs, request=request)
        queryset = filter_set.qs

        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        return render(request, 'apps/app_basic_research/list.html', {
            'page_obj': page_obj,
            'filter': filter_set,
            'current_sort': request.GET.get('sort', ''),
        })


# ==========================================
# 2. 创建预研项目
# ==========================================
class ResearchProjectCreateView(BasicResearchAccessMixin, CreateView):
    """创建预研：需具备 add 权限"""
    permission_required = 'app_basic_research.add_researchproject'
    model = ResearchProject
    form_class = ResearchProjectForm
    template_name = 'apps/app_basic_research/project_form.html'

    def form_valid(self, form):
        form.instance.manager = self.request.user
        response = super().form_valid(form)
        
        # 初始化流程节点
        project = self.object
        stages = [
            ResearchStage.INIT,
            ResearchStage.LITERATURE,
            ResearchStage.PLANNING,
            ResearchStage.EXPERIMENT,
            ResearchStage.ANALYSIS,
            ResearchStage.CONCLUSION
        ]

        nodes = [ResearchProjectNode(
            project=project, stage=stage, order=idx + 1,
            status='DOING' if idx == 0 else 'PENDING'
        ) for idx, stage in enumerate(stages)]

        ResearchProjectNode.objects.bulk_create(nodes)
        return response

    def get_success_url(self):
        return reverse('basic_research_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 3. 更新预研项目
# ==========================================
class ResearchProjectUpdateView(BasicResearchAccessMixin, UpdateView):
    """更新预研：需具备 change 权限，且仅限本部门"""
    permission_required = 'app_basic_research.change_researchproject'
    model = ResearchProject
    form_class = ResearchProjectForm
    template_name = 'apps/app_basic_research/project_form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_object_permission(obj) # 安全校验
        return obj

    def get_success_url(self):
        return reverse('basic_research_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 4. 预研项目详情
# ==========================================
class ResearchProjectDetailView(BasicResearchAccessMixin, DetailView):
    """详情查看：拦截跨部门访问"""
    permission_required = 'app_basic_research.view_researchproject'
    model = ResearchProject
    template_name = 'apps/app_basic_research/detail.html'
    context_object_name = 'project'

    queryset = ResearchProject.objects.select_related('manager').prefetch_related(
        'nodes', 'formulas', 'formulas__test_results', 'formulas__test_results__test_config'
    )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_object_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        current_std = self.request.GET.get('std', 'ISO')

        # 挂载配方物性 (逻辑保持不变)
        related_formulas = project.formulas.all().order_by('-created_at')
        for f in related_formulas:
            props = {}
            for res in f.test_results.all():
                if current_std not in res.test_config.standard and 'OTHER' not in res.test_config.standard: continue
                name = res.test_config.name
                if '密度' in name: props['density'] = res.value
                elif '熔融' in name: props['melt'] = res.value
                elif '拉伸' in name: props['tensile'] = res.value
                elif '弯曲强度' in name: props['flex_strength'] = res.value
                elif '弯曲模量' in name: props['flex_modulus'] = res.value
                elif '冲击' in name: props['impact'] = res.value
                elif '热变形' in name: props['hdt'] = res.value
            f.display_props = props

        context.update({
            'nodes': project.cached_nodes,
            'related_formulas': related_formulas,
            'current_std': current_std,
            'cart_formula_ids': self.request.session.get('compare_cart', {}).get('formula', []),
        })
        return context


# ==========================================
# 5. 节点与附件操作
# ==========================================
class BasicResearchObjectView(BasicResearchAccessMixin, View):
    """内部通用视图：用于检查 project 权限"""
    permission_required = 'app_basic_research.change_researchproject'
    model = ResearchProject # 补全模型声明

    def get_project_and_check(self, project_id):
        project = get_object_or_404(ResearchProject, pk=project_id)
        self.check_object_permission(project)
        return project

class ResearchProjectNodeUpdateView(BasicResearchObjectView):
    template_name = 'apps/app_basic_research/detail/modal_box/_project_progress_update.html'

    def get(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        self.check_object_permission(node.project)
        return render(request, self.template_name, {'node': node, 'status_choices': ResearchProjectNode.STATUS_CHOICES})

    def post(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        self.check_object_permission(node.project)
        form = ResearchProjectNodeUpdateForm(request.POST, instance=node)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return render(request, self.template_name, {'node': node, 'status_choices': ResearchProjectNode.STATUS_CHOICES, 'form': form})

class ResearchNodeFailedView(BasicResearchObjectView):
    template_name = 'apps/app_basic_research/detail/modal_box/_project_progress_failed.html'

    def get(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        self.check_object_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        self.check_object_permission(node.project)
        node.perform_failure_logic(request.POST.get('remark', '实验不通过'))
        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
