from django.urls import include, path

from app_catalog.api.views import (
    CatalogBackgroundView,
    CatalogNavTreeView,
    MaterialDownloadView,
    router,
)

app_name = 'app_catalog'

urlpatterns = [
    path('nav-tree/', CatalogNavTreeView.as_view(), name='nav_tree'),
    path(
        'background/<str:kind>/<int:pk>/',
        CatalogBackgroundView.as_view(),
        name='background',
    ),
    path(
        'materials/<int:pk>/download/<str:file_type>/',
        MaterialDownloadView.as_view(),
        name='material_download',
    ),
    path('', include(router.urls)),
]
