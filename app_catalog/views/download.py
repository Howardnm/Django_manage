from django.views.generic import View
from django.shortcuts import get_object_or_404, redirect
from django.http import Http404
from ..models import CatalogProduct, VisitorLog
from ..services.material_api import client
from ..api.views import push_member_activity_feedback

class MaterialDownloadView(View):
    """
    处理物料文档的安全下载，并回传行为给主系统
    """
    def get(self, request, pk, file_type):
        product = get_object_or_404(CatalogProduct, pk=pk, is_published=True)
        member_token = self.request.session.get('member_token')
        
        # 1. 记录本地下载行为
        VisitorLog.objects.create(
            product=product,
            visitor_ip=self.request.META.get('REMOTE_ADDR'),
            member_token=member_token,
            action='DOWNLOAD'
        )
        
        product.download_count += 1
        product.save(update_fields=['download_count'])
        
        # 2. 回传反馈给主系统
        if member_token:
            action_desc = f"DOWNLOAD_{file_type.upper()}"
            push_member_activity_feedback(member_token, action_desc, product.display_name)
        
        # 3. 执行实际重定向
        remote_data = client.get_material_detail(product.remote_material_id)
        if not remote_data:
            raise Http404("无法从主系统获取物料详情")
            
        file_url = remote_data.get(f'file_{file_type}')
        if not file_url:
            raise Http404(f"该物料未提供 {file_type.upper()} 核心文档")

        return redirect(file_url)
