from django.urls import path
from . import views

urlpatterns = [
    # 1. 通知列表页
    path('', views.NotificationListView.as_view(), name='notification_list'),
    
    # 2. 将单条通知标记为已读
    path('mark-as-read/<int:pk>/', views.mark_as_read, name='notification_mark_as_read'),
    
    # 3. 将所有通知标记为已读
    path('mark-all-as-read/', views.MarkAllAsReadView.as_view(), name='notification_mark_all_as_read'),
]
