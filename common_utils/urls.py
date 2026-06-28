"""
通用工具 URL 路由。

Routes:
    /common/api/search/      — MaterialAutocompleteView (name: common_autocomplete)
    /common/api/user-tree/   — UserTreeAPIView            (name: user_tree_api)
"""

from django.urls import path
from .views import MaterialAutocompleteView, UserTreeAPIView

urlpatterns = [
    path('api/search/', MaterialAutocompleteView.as_view(), name='common_autocomplete'),
    path('api/user-tree/', UserTreeAPIView.as_view(), name='user_tree_api'),
]
