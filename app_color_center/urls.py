from django.urls import path
from app_color_center.views import (
    ColorMatchingListView, ColorTaskDetailView,
    ColorTaskStartView, ColorBOMFillView, ColorTaskCompleteView,
)

app_name = 'color_center'

urlpatterns = [
    path('', ColorMatchingListView.as_view(), name='list'),
    path('<int:order_pk>/', ColorTaskDetailView.as_view(), name='detail'),
    path('<int:order_pk>/start/', ColorTaskStartView.as_view(), name='start'),
    path('<int:order_pk>/fill/', ColorBOMFillView.as_view(), name='fill'),
    path('<int:order_pk>/complete/', ColorTaskCompleteView.as_view(), name='complete'),
]
