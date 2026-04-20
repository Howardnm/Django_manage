from django.views import View
from django.shortcuts import get_object_or_404, redirect
from django.http import Http404, StreamingHttpResponse
from ..models import CatalogProduct, VisitorLog
from ..services.material_api import client
from ..services.feedback_service import FeedbackService

class MaterialDownloadView(View):
    """
    中转下载视图：作为代理向主系统请求文件流。
    采用对象模块化 Service 进行通信和行为回传。
    """
    def get(self, request, pk, file_type):
        # 1. 查找产品，确保已发布
        product = get_object_or_404(CatalogProduct, pk=pk, is_published=True)
        member_token = request.session.get('member_token')
        
        # 2. 核心准入：必须是已登录会员
        if not member_token:
            # 记录尝试下载但未登录的行为 (可选)
            login_url = redirect('app_catalog:login').url
            return redirect(f"{login_url}?next={request.path}")

        # 3. 行为审计 (本地与主系统)
        VisitorLog.objects.create(
            product=product,
            visitor_ip=request.META.get('REMOTE_ADDR'),
            member_token=member_token,
            action='DOWNLOAD'
        )
        
        product.download_count += 1
        product.save(update_fields=['download_count'])
        
        # 使用模块化 Service 回传下载行为
        FeedbackService.push_activity(member_token, f"DOWNLOAD_{file_type.upper()}", product.display_name)
        
        # 4. 获取远程流
        # 调用低代码语义化方法
        response = client.request_file_stream(product.remote_material_id, file_type)
        
        if not response or response.status_code != 200:
            raise Http404(f"主系统当前无法提供 {file_type.upper()} 文件，请稍后再试。")

        # 5. 安全中转传输 (Streaming)
        proxy_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get('Content-Type', 'application/pdf')
        )
        
        # 保持文件名一致性
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            proxy_response['Content-Disposition'] = content_disposition
        else:
            filename = f"{product.display_name}_{file_type.upper()}.pdf"
            proxy_response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return proxy_response
