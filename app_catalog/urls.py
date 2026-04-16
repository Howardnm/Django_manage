from django.urls import path, include
from .views import catalog, download

app_name = 'app_catalog'

urlpatterns = [
    # 核心展示与搜索
    path('', catalog.CatalogListView.as_view(), name='home'),
    path('search/', catalog.CatalogListView.as_view(), name='search'),
    
    # 详情页
    path('p/<int:pk>/', catalog.CatalogDetailView.as_view(), name='product_detail'),
    
    # 【新增】会员鉴权
    path('login/', catalog.MemberLoginView.as_view(), name='login'),
    path('logout/', catalog.MemberLogoutView.as_view(), name='logout'),
    
    # 文档下载
    path('download/<int:pk>/<str:file_type>/', download.MaterialDownloadView.as_view(), name='material_download'),
    
    # Webhook API
    path('api/', include('app_catalog.api.urls')),
]
