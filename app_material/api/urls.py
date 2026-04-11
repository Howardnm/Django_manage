from django.urls import path, include
from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register(r'types', views.MaterialTypeViewSet)
router.register(r'scenarios', views.ApplicationScenarioViewSet)
router.register(r'metric-categories', views.MetricCategoryViewSet)
router.register(r'test-configs', views.TestConfigViewSet)
router.register(r'materials', views.MaterialLibraryViewSet)
router.register(r'data-points', views.MaterialDataPointViewSet)
router.register(r'files', views.MaterialFileViewSet)

app_name = 'app_material_api'

urlpatterns = [
    path('', include(router.urls)),
]
