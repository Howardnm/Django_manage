"""工艺方案参数预填。

建议路由（本文件不注册）::

    path(
        'orders/process-profiles/<int:pk>/params/',
        ProcessProfileParamsView.as_view(),
        name='trial_process_profile_params',
    )
"""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View

from app_process.models import ProcessProfile
from app_trial_production.mixins import TrialProductionAccessMixin


class ProcessProfileParamsView(TrialProductionAccessMixin, View):
    """GET：按主键返回工艺方案参数，供工单页换方案时覆盖输入框。

    登录且通过试验排产模块准入即可，不另设 permission_required。
    """

    def get(self, request, pk):
        profile = get_object_or_404(
            ProcessProfile.objects.select_related('machine', 'screw_combination'),
            pk=pk,
        )
        data = {
            'name': profile.name,
            'machine': str(profile.machine) if profile.machine_id else '',
            'screw_combination': (
                str(profile.screw_combination) if profile.screw_combination_id else ''
            ),
        }
        for field_name in ProcessProfile.ALL_PARAM_FIELDS:
            data[field_name] = getattr(profile, field_name)
        return JsonResponse(data)
