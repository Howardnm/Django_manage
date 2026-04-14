import json
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import get_object_or_404, redirect
from .models.material import (MaterialType, ApplicationScenario, MetricCategory, TestConfig, 
                    MaterialDataPoint, MaterialFile, MaterialLibrary, MaterialCharacteristic)
from .models.sync import WebhookTask

@admin.register(MaterialCharacteristic)
class MaterialCharacteristicAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(MaterialType)
class MaterialTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'classification', 'description')
    search_fields = ('name', 'classification')
    list_filter = ('classification',)

@admin.register(ApplicationScenario)
class ApplicationScenarioAdmin(admin.ModelAdmin):
    list_display = ('name', 'requirements')
    search_fields = ('name',)

@admin.register(MetricCategory)
class MetricCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    ordering = ('order',)

@admin.register(TestConfig)
class TestConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'standard', 'condition', 'unit', 'data_type', 'order')
    list_filter = ('category', 'data_type')
    search_fields = ('name', 'standard')
    ordering = ('category__order', 'order')

class MaterialDataPointInline(admin.TabularInline):
    model = MaterialDataPoint
    extra = 1
    autocomplete_fields = ['test_config']

class MaterialFileInline(admin.TabularInline):
    model = MaterialFile
    fields = ('file', 'name', 'file_type', 'version', 'description')
    extra = 1

@admin.register(MaterialLibrary)
class MaterialLibraryAdmin(admin.ModelAdmin):
    # 增加 is_published 到展示列表并允许直接编辑
    list_display = ('grade_name', 'manufacturer', 'category', 'flammability', 'is_published', 'file_tds', 'file_msds', 'file_rohs', 'created_at')
    list_editable = ('is_published',)
    search_fields = ('grade_name', 'manufacturer')
    list_filter = ('is_published', 'category', 'flammability', 'scenarios', 'characteristics', 'created_at')
    filter_horizontal = ('scenarios', 'characteristics')
    inlines = [MaterialDataPointInline, MaterialFileInline]
    autocomplete_fields = ['category']

@admin.register(WebhookTask)
class WebhookTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'status', 'retry_count', 'display_payload_summary', 'created_at', 'updated_at', 'requeue_action')
    list_filter = ('status', 'event_type')
    readonly_fields = ('event_type', 'payload', 'last_error', 'created_at', 'updated_at', 'retry_count', 'max_retries')
    search_fields = ('event_type', 'payload', 'last_error')
    
    fieldsets = (
        (None, {'fields': ('event_type', 'status', 'retry_count', 'max_retries', 'created_at', 'updated_at')}),
        ('Payload 详情', {'fields': ('formatted_payload',), 'classes': ('collapse',)}),
        ('错误信息', {'fields': ('last_error',), 'classes': ('collapse',)}),
    )

    def formatted_payload(self, obj):
        try:
            return format_html('<pre style="background-color:#f8f8f8; padding:10px; border:1px solid #eee; white-space:pre-wrap; word-break:break-all;">{}</pre>', json.dumps(json.loads(obj.payload), indent=2, ensure_ascii=False))
        except Exception:
            return obj.payload
    formatted_payload.short_description = 'Payload 内容'

    def display_payload_summary(self, obj):
        try:
            data = json.loads(obj.payload).get('data', {})
            return f"ID: {data.get('id')} | {data.get('grade_name') or data.get('name')}"
        except Exception:
            return obj.payload[:50]
    display_payload_summary.short_description = '摘要'

    def requeue_action(self, obj):
        if obj.status == 'FAILED':
            url = reverse('admin:app_material_webhooktask_requeue', args=[obj.pk])
            return format_html('<a class="button" href="{}">手动重试</a>', url)
        return "-"
    requeue_action.short_description = '操作'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/requeue/', self.admin_site.admin_view(self.requeue_view), name='app_material_webhooktask_requeue'),
        ]
        return custom_urls + urls

    def requeue_view(self, request, object_id):
        task = get_object_or_404(WebhookTask, pk=object_id)
        task.status = 'PENDING'
        task.retry_count = 0
        task.save()
        self.message_user(request, f"任务 {object_id} 已重置。")
        return redirect('admin:app_material_webhooktask_changelist')
