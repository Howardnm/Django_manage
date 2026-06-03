from django.contrib import admin

from .models.sap_cache import SapSyncLog
from .models.sap_config import SapConnectionConfig


@admin.register(SapSyncLog)
class SapSyncLogAdmin(admin.ModelAdmin):
    list_display = ['function_type', 'rfc_name', 'status',
                    'records_synced', 'duration_ms', 'created_at']
    list_filter = ['status', 'function_type']
    search_fields = ['rfc_name', 'error_message']
    readonly_fields = ['created_at']


@admin.register(SapConnectionConfig)
class SapConnectionConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'ashost', 'user', 'is_active', 'updated_at']
    list_filter = ['is_active']
