from django.urls import path, include
from .views import catalog, download

app_name = 'app_catalog'

view_patterns = [
    # 首页：应用场景导向
    path('', catalog.CatalogHomeView.as_view(), name='home'),
    
    # 二级：场景下的材质分类
    path('scenario/<int:scenario_id>/', catalog.ScenarioCategoryView.as_view(), name='scenario_categories'),
    
    # 三级：场景+材质下的牌号列表
    path('scenario/<int:scenario_id>/category/<int:category_id>/', catalog.CatalogListView.as_view(), name='product_list'),
    
    # 独立牌号列表 (全线产品 / 搜索)
    path('all-products/', catalog.CatalogListView.as_view(), name='search'),
    
    # 详情页 (保持 URL 简洁)
    path('p/<int:pk>/', catalog.CatalogDetailView.as_view(), name='product_detail'),
    
    # 文档下载
    path('download/<int:pk>/<str:file_type>/', download.MaterialDownloadView.as_view(), name='material_download'),
]

api_patterns = [
    # Webhook 等 API 逻辑
    path('api/', include('app_catalog.api.urls')),
]

urlpatterns = view_patterns + api_patterns
