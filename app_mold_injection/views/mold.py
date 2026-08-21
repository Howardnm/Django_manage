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
    permission_required = 'app_mold_injection.view_moldtype'

    def get_queryset(self):
        # 模具台账不做 L4/L5 数据隔离，纯模块准入（L1+L2+L3）把关。
        return self.model.objects.all()


class MoldTypeCreateView(MoldManageAccessMixin, CreateView):
    """添加模具"""
    model = MoldType
    form_class = MoldTypeForm
    template_name = 'apps/app_mold_injection/mold/form.html'
    success_url = reverse_lazy('mold_injection:mold_list')
    permission_required = 'app_mold_injection.add_moldtype'

    def get_queryset(self):
        # MoldType 无所有者字段，数据隔离不适用；返回全量集避免 L4/L5 假告警。
        return self.model.objects.all()


class MoldTypeUpdateView(MoldManageAccessMixin, UpdateView):
    """编辑模具"""
    model = MoldType
    form_class = MoldTypeForm
    template_name = 'apps/app_mold_injection/mold/form.html'
    success_url = reverse_lazy('mold_injection:mold_list')
    permission_required = 'app_mold_injection.change_moldtype'

    def get_queryset(self):
        # MoldType 无所有者字段，数据隔离不适用；返回全量集避免 L4/L5 假告警。
        return self.model.objects.all()