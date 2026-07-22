from django.urls import path
from . import views

urlpatterns = [
    # 表单模板管理
    path('', views.FormTemplateListView.as_view(), name='form_template_list'),
    path('create/', views.FormTemplateCreateView.as_view(), name='form_template_create'),
    path('new/', views.FormCreateWizardView.as_view(), name='form_create_wizard'),
    path('api/entities/', views.EntitySearchView.as_view(), name='form_entity_search'),
    path('api/upload/', views.FormUploadView.as_view(), name='form_upload'),
    path('api/upload/delete/', views.FormUploadDeleteView.as_view(), name='form_upload_delete'),
    path('<int:pk>/edit/', views.FormTemplateUpdateView.as_view(), name='form_template_edit'),
    path('<int:pk>/update_info/', views.FormTemplateBasicInfoUpdateView.as_view(), name='form_template_update_info'),
    path('<int:pk>/delete/', views.FormTemplateDeleteView.as_view(), name='form_template_delete'),
    path('<int:pk>/', views.FormTemplateDetailView.as_view(), name='form_template_detail'),

    # 表单填写
    path('<int:template_pk>/fill/', views.FormSubmissionCreateView.as_view(), name='form_submission_fill'),

    # 编辑已有提交（草稿/退回修订）
    path('<int:template_pk>/fill/<int:submission_pk>/edit/',
         views.FormSubmissionCreateView.as_view(),
         name='form_submission_edit'),

    # 表单填写 — 关联目标对象（目标别名来自 registry.py 白名单）
    path('<int:template_pk>/fill/<str:target_alias>/<int:obj_pk>/',
         views.FormSubmissionCreateView.as_view(),
         name='form_submission_fill_target'),

    # 我的表单
    path('my/drafts/', views.MyDraftsView.as_view(), name='my_drafts'),
    path('my/submissions/', views.MySubmissionsView.as_view(), name='my_submissions'),

    # 提交记录
    path('submission/<int:pk>/', views.FormSubmissionDetailView.as_view(), name='form_submission_detail'),
    path('submission/<int:pk>/delete/', views.FormSubmissionDeleteView.as_view(), name='form_submission_delete'),
]
