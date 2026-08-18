from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .registry import register_urls

router = DefaultRouter()
register_urls(router)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/verify/', views.MemberAuthVerifyView.as_view(), name='api_member_verify'),
    path('auth/feedback/', views.MemberActivityFeedbackView.as_view(), name='api_member_feedback'),
    path('catalog/nav-tree/', views.CatalogNavTreeView.as_view(), name='api_catalog_nav_tree'),
    path('cache-version/', views.CacheVersionView.as_view(), name='api_cache_version'),
    path('materials/<int:pk>/download/<str:file_type>/',
         views.MaterialInternalDownloadView.as_view(), name='api_material_download'),
]
