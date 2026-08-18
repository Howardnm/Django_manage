from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html

from .models import ExternalMemberActivity

User = get_user_model()


@admin.register(ExternalMemberActivity)
class ExternalMemberActivityAdmin(admin.ModelAdmin):
    list_display = ('member_identity', 'action_label', 'target_name', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('member_token', 'target_name')
    readonly_fields = ('member_token', 'action', 'target_name', 'timestamp')

    def member_identity(self, obj):
        user = User.objects.filter(member_token=obj.member_token).select_related(
            'associated_customer', 'associated_oem'
        ).first()
        if user:
            if user.associated_customer_id:
                return format_html(
                    '<span class="badge bg-blue-lt">客户: {} ({})</span>',
                    user.associated_customer.company_name, user.get_full_name() or user.username,
                )
            if user.associated_oem_id:
                return format_html(
                    '<span class="badge bg-azure-lt">主机厂: {} ({})</span>',
                    user.associated_oem.name, user.get_full_name() or user.username,
                )
            return format_html('<span class="badge bg-green-lt">内部员工: {}</span>', user.username)
        return f"未知令牌: {obj.member_token[:8]}"

    def action_label(self, obj):
        color = 'red' if 'DOWNLOAD' in obj.action else 'azure'
        return format_html('<span class="badge bg-{}-lt">{}</span>', color, obj.action)

    member_identity.short_description = '访问者身份'
    action_label.short_description = '行为'
