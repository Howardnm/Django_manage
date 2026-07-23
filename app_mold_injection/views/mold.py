from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from app_mold_injection.mixins import MoldManageAccessMixin
from app_mold_injection.models import MoldType
from app_mold_injection.forms import MoldTypeForm


class MoldTypeListView(MoldManageAccessMixin, ListView):
    """模具台账列表"""
    model = MoldType
    template_name = 'apps/app_mold_injection/mold/list.html'
    context_object_name = 'molds'
    paginate_by = 20
    enforce_dept_isolation = False


class MoldTypeCreateView(MoldManageAccessMixin, CreateView):
    """添加模具"""
    model = MoldType
    form_class = MoldTypeForm
    template_name = 'apps/app_mold_injection/mold/form.html'
    success_url = reverse_lazy('mold_injection:mold_list')
    permission_required = 'app_mold_injection.add_moldtype'


class MoldTypeUpdateView(MoldManageAccessMixin, UpdateView):
    """编辑模具"""
    model = MoldType
    form_class = MoldTypeForm
    template_name = 'apps/app_mold_injection/mold/form.html'
    success_url = reverse_lazy('mold_injection:mold_list')
    permission_required = 'app_mold_injection.change_moldtype'
