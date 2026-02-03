from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View

from app_repository.forms import OEMForm, OEMStandardFileForm
from app_repository.models import OEM, OEMStandardFile
from app_repository.utils.filters import OEMFilter

# ==========================================
# 1. 主机厂列表
# ==========================================
class OEMListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_oem'
    model = OEM
    template_name = 'apps/app_repository/oem/oem_list.html'
    context_object_name = 'oems'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('name')
        self.filterset = OEMFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context

# ==========================================
# 2. 主机厂详情
# ==========================================
class OEMDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_repository.view_oem'
    model = OEM
    template_name = 'apps/app_repository/oem/oem_detail.html'
    context_object_name = 'oem'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('standard_files__uploader')

# ==========================================
# 3. 创建与更新
# ==========================================
class OEMCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_oem'
    raise_exception = True
    model = OEM
    form_class = OEMForm
    template_name = 'apps/app_repository/form_generic.html'

    def get_success_url(self):
        return reverse('repo_oem_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增主机厂 (OEM)'
        return context

class OEMUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_oem'
    raise_exception = True
    model = OEM
    form_class = OEMForm
    template_name = 'apps/app_repository/form_generic.html'

    def get_success_url(self):
        return reverse('repo_oem_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑主机厂: {self.object.name}'
        return context

# ==========================================
# 4. 附件管理 (HTMX优化)
# ==========================================
class OEMStandardFileFormView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """【新增】用于HTMX加载模态框内容的视图"""
    permission_required = 'app_repository.change_oem'

    def get(self, request, pk):
        oem = get_object_or_404(OEM, pk=pk)
        form = OEMStandardFileForm()
        return render(request, 'apps/app_repository/oem/_modal_file_upload.html', {'oem': oem, 'form': form}) # 传递 form 变量名

class OEMStandardFileUploadView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_repository.change_oem'

    def post(self, request, pk):
        oem = get_object_or_404(OEM, pk=pk)
        form = OEMStandardFileForm(request.POST, request.FILES)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.oem = oem
            instance.uploader = request.user
            instance.save()
            # 【HTMX优化】成功后返回特殊响应，关闭模态框并刷新文件列表
            return HttpResponse(status=204, headers={
                'HX-Trigger': 'fileUploaded', # 触发一个自定义事件
                'HX-Refresh': 'true' # 刷新整个页面，或者更精确地刷新文件列表容器
            })
        else:
            # 【HTMX优化】如果表单无效，重新渲染模态框内容，显示错误信息
            return render(request, 'apps/app_repository/oem/_modal_file_upload.html', {'oem': oem, 'form': form})

class OEMStandardFileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_repository.change_oem'

    def post(self, request, pk):
        file_obj = get_object_or_404(OEMStandardFile, pk=pk)
        oem_pk = file_obj.oem.pk
        file_obj.delete()
        # 【HTMX优化】返回特殊响应，刷新文件列表
        return HttpResponse(status=204, headers={
            'HX-Trigger': 'fileDeleted', # 触发一个自定义事件
            'HX-Refresh': 'true' # 刷新整个页面，或者更精确地刷新文件列表容器
        })
