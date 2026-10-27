"""成品 BOM 发布 / 下架页。独立 HTML，不继承系统模板。"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class FinishedBomSyncView(LoginRequiredMixin, TemplateView):
    template_name = "apps/app_material/finished_bom_sync.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_sap_code"] = (self.request.GET.get("sap_code") or "").strip()
        return context
