from django.views import View
from django.shortcuts import get_object_or_404
from django.http import Http404, StreamingHttpResponse
from ..models import CatalogProduct, VisitorLog
from ..services.material_api import client
from ..api.views import push_member_activity_feedback

class MaterialDownloadView(View):
    """
    中转下载视图：作为代理向主系统请求文件流。
    满足后期独立部署需求，不暴露主系统物理文件地址。
    """
    def get(self, request, pk, file_type):
        # 1. 查找产品，确保已发布
        product = get_object_or_404(CatalogProduct, pk=pk, is_published=True)
        member_token = self.request.session.get('member_token')
        
        # 2. 身份校验逻辑 (如果是独立运行系统，此处需根据 CatalogMember 逻辑检查)
        # 此处假设只有登录会员或在特定 session 下才能下载
        # if not member_token:
        #     raise PermissionDenied("请先登录后下载技术文档")

        # 3. 记录日志 (本地)
        VisitorLog.objects.create(
            product=product,
            visitor_ip=self.request.META.get('REMOTE_ADDR'),
            member_token=member_token,
            action='DOWNLOAD'
        )
        
        product.download_count += 1
        product.save(update_fields=['download_count'])
        
        # 4. 回传反馈给主系统
        if member_token:
            action_desc = f"DOWNLOAD_{file_type.upper()}"
            push_member_activity_feedback(member_token, action_desc, product.display_name)
        
        # 5. 从主系统获取流
        # 注意：这里调用的是我们刚刚在 client 增加的方法
        response = client.stream_file_download(product.remote_material_id, file_type)
        
        if not response:
            raise Http404(f"主系统未提供或无权访问该 {file_type.upper()} 文件")

        # 6. 流式中转给最终用户
        proxy_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get('Content-Type')
        )
        
        # 提取原文件名称或构建新名称
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            proxy_response['Content-Disposition'] = content_disposition
        else:
            filename = f"{product.display_name}_{file_type.upper()}.pdf"
            proxy_response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return proxy_response
