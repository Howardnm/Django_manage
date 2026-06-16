from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'types', views.MaterialTypeViewSet)
router.register(r'scenarios', views.ApplicationScenarioViewSet)
router.register(r'categories', views.MetricCategoryViewSet)
router.register(r'test-configs', views.TestConfigViewSet)
router.register(r'materials', views.MaterialLibraryViewSet)
router.register(r'data-points', views.MaterialDataPointViewSet)
router.register(r'files', views.AttachmentFileViewSet, basename='attachment')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/verify/', views.MemberAuthVerifyView.as_view(), name='api_member_verify'),
    path('auth/feedback/', views.MemberActivityFeedbackView.as_view(), name='api_member_feedback'),
    
    # 增加内部下载接口
    path('materials/<int:pk>/download/<str:file_type>/', views.MaterialInternalDownloadView.as_view(), name='api_material_download'),
]
