from django.contrib import admin
from ..models import VisitorLog

@admin.register(VisitorLog)
class VisitorLogAdmin(admin.ModelAdmin):
    list_display = ('product', 'visitor_ip', 'action', 'timestamp')
    list_filter = ('action', 'timestamp')
    readonly_fields = ('product', 'visitor_ip', 'user_agent', 'action', 'timestamp')
