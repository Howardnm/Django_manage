from django.views.generic import View
from django.shortcuts import get_object_or_404, redirect
from django.http import Http404
from ..models import CatalogProduct, VisitorLog
from ..services.material_api import client

class MaterialDownloadView(View):
    """
    处理物料文档的安全下载
    逻辑：记录本地下载行为，然后重定向到主系统提供的绝对 URL
    """
    def get(self, request, pk, file_type):
        # 1. 查找本地镜像产品
        product = get_object_or_404(CatalogProduct, pk=pk, is_published=True)
        
        # 2. 记录访客下载日志 (本地)
        VisitorLog.objects.create(
            product=product,
            visitor_ip=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            action='DOWNLOAD'
        )
        
        # 3. 增加本地下载计数
        product.download_count += 1
        product.save(update_fields=['download_count'])
        
        # 4. 从 API 实时获取文件下载地址
        remote_data = client.get_material_detail(product.remote_material_id)
        if not remote_data:
            raise Http404("无法从主系统获取物料详情，数据可能已同步或 API 暂时不可用")
            
        # 5. 获取文件字段 (与 app_material/api/serializers.py 保持一致)
        # 字段名可能是 file_tds, file_msds, file_rohs
        file_url = remote_data.get(f'file_{file_type}')

        if not file_url:
            raise Http404(f"该物料在主系统中未提供 {file_type.upper()} 核心文档")

        # 6. 执行重定向 (由于是绝对 URL，直接 redirect 即可)
        return redirect(file_url)
