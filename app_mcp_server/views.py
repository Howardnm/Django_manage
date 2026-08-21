import logging
import json
from django.conf import settings
from django.http import StreamingHttpResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from .transports.sse import mcp_sse_generator
from .transports.http import process_mcp_message
from .core.sessions import session_manager

# 设置日志
logger = logging.getLogger(__name__)

def add_cors_headers(response):
    """为响应添加通用的 CORS 允许头"""
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, X-MCP-API-KEY, Authorization'
    response['Access-Control-Expose-Headers'] = '*'
    return response

def check_auth(request):
    """安全认证拦截器 (X-MCP-API-KEY)"""
    expected_key = getattr(settings, "MCP_API_KEY", None)
    if not expected_key:
        return True
    return request.headers.get("X-MCP-API-KEY") == expected_key

@csrf_exempt
async def sse_endpoint(request):
    """建立 SSE 连接: GET /mcp/sse/"""
    if not check_auth(request):
        return HttpResponseForbidden("Authentication Required")

    session_id = session_manager.create_session()
    logger.info(f"Establishing MCP SSE Connection. Session ID: {session_id}")

    response = StreamingHttpResponse(
        mcp_sse_generator(request, session_id), 
        content_type="text/event-stream"
    )
    
    # SSE 标准响应头
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no' # 告知 Nginx 不要缓冲
    return add_cors_headers(response)

@csrf_exempt
async def messages_endpoint(request):
    """处理消息发送: POST /mcp/messages/"""
    if request.method == "OPTIONS":
        return add_cors_headers(HttpResponse())

    if not check_auth(request):
        return add_cors_headers(HttpResponseForbidden("Auth Required"))

    if request.method != "POST":
        return add_cors_headers(HttpResponse(status=405))

    session_id = request.GET.get("sessionId")
    if not session_id:
        return add_cors_headers(HttpResponseBadRequest("Missing Session ID"))
        
    try:
        success = await process_mcp_message(session_id, request.body)
        if success:
            return add_cors_headers(HttpResponse(status=202))
        else:
            return add_cors_headers(HttpResponseBadRequest("Invalid or Expired Session ID"))
            
    except Exception as e:
        logger.error(f"Error handling message for {session_id}: {str(e)}", exc_info=True)
        return add_cors_headers(HttpResponse(content=str(e), status=400))
