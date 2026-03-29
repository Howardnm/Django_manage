import logging
from django.conf import settings
from django.http import StreamingHttpResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from .transports.sse import mcp_sse_generator
from .transports.http import process_mcp_message
from .core.sessions import session_manager

# 设置日志
logger = logging.getLogger("app_mcp_server.views")

def check_auth(request):
    """安全认证拦截器 (X-MCP-API-KEY)"""
    expected_key = getattr(settings, "MCP_API_KEY", None)
    if not expected_key:
        return True
    return request.headers.get("X-MCP-API-KEY") == expected_key

async def sse_endpoint(request):
    """建立 SSE 连接: GET /mcp/sse/"""
    if not check_auth(request):
        return HttpResponseForbidden("Authentication Required")

    # 创建新的会话 ID 并启动生成器
    session_id = session_manager.create_session()
    logger.info(f"Establishing MCP SSE Connection. Session ID: {session_id}")

    response = StreamingHttpResponse(
        mcp_sse_generator(request, session_id), 
        content_type="text/event-stream"
    )
    
    # SSE 标准响应头，优化实时性和禁用代理缓存
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Access-Control-Allow-Origin'] = '*'
    return response

@csrf_exempt
async def messages_endpoint(request):
    """处理消息发送: POST /mcp/messages/"""
    if not check_auth(request):
        return HttpResponseForbidden("Auth Required")

    if request.method == "OPTIONS":
        response = HttpResponse()
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-MCP-API-KEY'
        return response

    if request.method != "POST":
        return HttpResponse(status=405)

    session_id = request.GET.get("sessionId")
    if not session_id:
        return HttpResponseBadRequest("Missing Session ID")
        
    try:
        # 通过传输层分发消息
        success = await process_mcp_message(session_id, request.body)
        if success:
            return HttpResponse(status=202)
        else:
            return HttpResponseBadRequest("Invalid or Expired Session ID")

    except Exception as e:
        logger.error(f"Error handling message for {session_id}: {str(e)}", exc_info=True)
        return HttpResponse(content=str(e), status=400)
