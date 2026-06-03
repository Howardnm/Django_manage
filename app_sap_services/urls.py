"""SAP 集成服务 URL 路由 — 提供内部 API 供其他模块或前端调用"""

from django.urls import path

from . import views

urlpatterns = [
    # 健康检查
    path('health/', views.SapHealthView.as_view(), name='sap_health'),

    # 物料查询 API
    path('material/<str:material_code>/', views.MaterialDetailView.as_view(),
         name='sap_material_detail'),
    path('material/<str:material_code>/stock/', views.MaterialStockView.as_view(),
         name='sap_material_stock'),

    # 同步日志
    path('sync-logs/', views.SyncLogListView.as_view(), name='sap_sync_logs'),
]
