from django.shortcuts import render
from django.views import View
from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class ChatbotView(UnifiedAccessMixin, View):
    identity_required = IdentityConfig.INTERNAL_STAFF

    def get(self, request):
        return render(request, 'apps/app_dify_sync/chatbot.html')
