from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_process.models import ProcessType
from app_process.forms import ProcessTypeForm

class ProcessTypeListView(LoginRequiredMixin, ListView):
    model = ProcessType
    template_name = 'apps/app_process/type/list.html'
    context_object_name = 'types'
    paginate_by = 20

class ProcessTypeCreateView(LoginRequiredMixin, CreateView):
    model = ProcessType
    form_class = ProcessTypeForm
    template_name = 'apps/app_process/type/form.html'
    success_url = reverse_lazy('process_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增工艺类型'
        return context

    def form_valid(self, form):
        messages.success(self.request, "工艺类型已添加")
        return super().form_valid(form)

class ProcessTypeUpdateView(LoginRequiredMixin, UpdateView):
    model = ProcessType
    form_class = ProcessTypeForm
    template_name = 'apps/app_process/type/form.html'
    success_url = reverse_lazy('process_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑工艺类型'
        return context

    def form_valid(self, form):
        messages.success(self.request, "工艺类型已更新")
        return super().form_valid(form)
