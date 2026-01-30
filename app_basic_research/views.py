from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView, DetailView
from django.http import HttpResponse

from app_basic_research.forms import ResearchProjectForm, ResearchProjectNodeUpdateForm, ResearchProjectFileForm
from app_basic_research.models import ResearchProject, ResearchStage, ResearchProjectNode, ResearchProjectFile
from app_basic_research.utils.filters import ResearchProjectFilter


# ==========================================
# 1. 预研项目列表
# ==========================================
class ResearchProjectListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_basic_research.view_researchproject'

    def get(self, request):
        # 1. 基础查询集
        base_qs = ResearchProject.objects.select_related('manager').order_by('-created_at')

        # 2. 接入 Filter
        filter_set = ResearchProjectFilter(request.GET, queryset=base_qs, request=request)
        queryset = filter_set.qs

        # 3. 分页
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'page_obj': page_obj,
            'filter': filter_set,
            'current_sort': request.GET.get('sort', ''),
        }
        return render(request, 'apps/app_basic_research/list.html', context)


# ==========================================
# 2. 创建预研项目
# ==========================================
class ResearchProjectCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_basic_research.add_researchproject'
    raise_exception = True

    model = ResearchProject
    form_class = ResearchProjectForm
    template_name = 'apps/app_basic_research/project_form.html'

    def form_valid(self, form):
        form.instance.manager = self.request.user
        response = super().form_valid(form)
        
        # 【核心修复】创建项目后，自动初始化预研项目的标准流程节点
        # 避免创建出空项目，或者混淆成普通项目
        project = self.object
        stages = [
            ResearchStage.INIT,
            ResearchStage.LITERATURE,
            ResearchStage.PLANNING,
            ResearchStage.EXPERIMENT,
            ResearchStage.ANALYSIS,
            ResearchStage.CONCLUSION
        ]

        nodes = []
        for index, stage in enumerate(stages):
            nodes.append(ResearchProjectNode(
                project=project,
                stage=stage,
                order=index + 1,
                status='DOING' if index == 0 else 'PENDING' # 第一个节点默认进行中
            ))

        ResearchProjectNode.objects.bulk_create(nodes)
        
        return response

    def get_success_url(self):
        return reverse('basic_research_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 3. 更新预研项目
# ==========================================
class ResearchProjectUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_basic_research.change_researchproject'
    raise_exception = True

    model = ResearchProject
    form_class = ResearchProjectForm
    template_name = 'apps/app_basic_research/project_form.html'

    def get_success_url(self):
        return reverse('basic_research_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 4. 预研项目详情
# ==========================================
class ResearchProjectDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_basic_research.view_researchproject'
    model = ResearchProject
    template_name = 'apps/app_basic_research/detail.html'
    context_object_name = 'project'

    # 【优化】预加载 formulas (关联配方) 及其测试结果，避免 N+1
    queryset = ResearchProject.objects.select_related('manager').prefetch_related(
        'nodes',
        'formulas',  # 关联的实验配方
        'formulas__test_results', # 配方的测试结果
        'formulas__test_results__test_config', # 测试配置
        'files' # 预加载附件
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        
        # 获取当前标准 (ISO/ASTM)，默认 ISO
        current_std = self.request.GET.get('std', 'ISO')

        # 处理关联配方的数据，提取关键物性
        related_formulas = project.formulas.all().order_by('-created_at')
        for f in related_formulas:
            # 动态挂载一个 display_props 属性，用于模板展示
            # 逻辑参考 app_repository/views/material_detail.py
            props = {}
            # 预加载的 test_results
            results = f.test_results.all()
            
            for res in results:
                t_name = res.test_config.name
                t_std = res.test_config.standard
                
                # 筛选标准
                if current_std not in t_std and 'OTHER' not in t_std:
                    continue
                    
                val = res.value
                
                # 关键词匹配 (简化版)
                if '密度' in t_name: props['density'] = val
                elif '熔融' in t_name: props['melt'] = val
                elif '拉伸' in t_name: props['tensile'] = val
                elif '弯曲强度' in t_name: props['flex_strength'] = val
                elif '弯曲模量' in t_name: props['flex_modulus'] = val
                elif '冲击' in t_name: props['impact'] = val
                elif '热变形' in t_name: props['hdt'] = val
            
            f.display_props = props

        context.update({
            'nodes': project.cached_nodes,
            'related_formulas': related_formulas,
            'current_std': current_std,
            # 获取购物车中的配方ID (如果 session 中有)
            'cart_formula_ids': self.request.session.get('compare_cart', {}).get('formula', []),
            # 附件表单
            'file_form': ResearchProjectFileForm()
        })
        return context


# ==========================================
# 5. 节点操作：常规更新
# ==========================================
class ResearchProjectNodeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_basic_research.change_researchproject'
    template_name = 'apps/app_basic_research/detail/modal_box/_project_progress_update.html'

    def get(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        return render(request, self.template_name, {
            'node': node,
            'status_choices': ResearchProjectNode.STATUS_CHOICES
        })

    def post(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        form = ResearchProjectNodeUpdateForm(request.POST, instance=node)

        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return render(request, self.template_name, {
            'node': node,
            'status_choices': ResearchProjectNode.STATUS_CHOICES,
            'form': form
        })


# ==========================================
# 6. 节点操作：申报不合格 (失败重开)
# ==========================================
class ResearchNodeFailedView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_basic_research.change_researchproject'
    template_name = 'apps/app_basic_research/detail/modal_box/_project_progress_failed.html'

    def get(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        node = get_object_or_404(ResearchProjectNode, pk=pk)
        remark = request.POST.get('remark', '实验不通过，需重新验证')

        # 业务逻辑已下沉到 Model
        node.perform_failure_logic(remark)

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})


# ==========================================
# 7. 附件上传
# ==========================================
class ResearchProjectFileUploadView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_basic_research.change_researchproject'

    def post(self, request, pk):
        project = get_object_or_404(ResearchProject, pk=pk)
        form = ResearchProjectFileForm(request.POST, request.FILES)
        
        if form.is_valid():
            instance = form.save(commit=False)
            instance.project = project
            instance.uploader = request.user
            instance.save()
            
        return redirect('basic_research_detail', pk=pk)


# ==========================================
# 8. 附件删除
# ==========================================
class ResearchProjectFileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_basic_research.change_researchproject'

    def post(self, request, pk):
        file_obj = get_object_or_404(ResearchProjectFile, pk=pk)
        project_pk = file_obj.project.pk
        file_obj.delete()
        return redirect('basic_research_detail', pk=project_pk)
