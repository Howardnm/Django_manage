from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def chatbot_view(request):
    """
    渲染嵌入了 Dify AI Agent 的聊天机器人页面。
    """
    return render(request, 'apps/app_dify_sync/chatbot.html')
