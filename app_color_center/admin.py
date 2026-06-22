from django.contrib import admin
from app_color_center.models import ColorMatchingTask


@admin.register(ColorMatchingTask)
class ColorMatchingTaskAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'operator', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['production_order__code']
