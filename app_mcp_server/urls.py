from django.urls import path
from .views import sse_endpoint, messages_endpoint

app_name = 'app_mcp_server'

urlpatterns = [
    # MCP Server 的 SSE 连接端点 (GET)
    path('sse/', sse_endpoint, name='mcp_sse'),
    
    # MCP Server 的消息处理端点 (POST)
    path('messages/', messages_endpoint, name='mcp_messages'),
]
