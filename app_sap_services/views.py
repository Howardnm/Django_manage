"""SAP 集成服务视图 — 提供内部 REST API 供前端或其他模块调用"""

import json
import logging

from django.http import JsonResponse
from django.views import View
from app_user.mixins import UnifiedAccessMixin

from .models.sap_cache import SapSyncLog
from .services.connection import connection_pool
from .services.material import SapMaterialService

logger = logging.getLogger('app_sap_services')


class SapHealthView(UnifiedAccessMixin, View):
    identity_required = ['ADMIN']
    permission_required = 'app_sap_services'

    def get(self, request):
        ok = connection_pool.health_check()
        return JsonResponse({'status': 'ok' if ok else 'unavailable'})


class MaterialDetailView(UnifiedAccessMixin, View):
    identity_required = ['ADMIN']
    permission_required = 'app_sap_services'

    def get(self, request, material_code):
        service = SapMaterialService()
        detail = service.get_material_detail(material_code)
        return JsonResponse({'data': detail})


class MaterialStockView(UnifiedAccessMixin, View):
    identity_required = ['ADMIN']
    permission_required = 'app_sap_services'

    def get(self, request, material_code):
        plant = request.GET.get('plant')
        location = request.GET.get('location')
        service = SapMaterialService()
        stock_data = service.get_stock(material_code, plant, location)
        return JsonResponse({'data': stock_data})


class SyncLogListView(UnifiedAccessMixin, View):
    identity_required = ['ADMIN']
    permission_required = 'app_sap_services'

    def get(self, request):
        logs = SapSyncLog.objects.all()[:50].values(
            'id', 'function_type', 'rfc_name', 'status',
            'records_synced', 'duration_ms', 'created_at',
        )
        return JsonResponse({'data': list(logs)})
