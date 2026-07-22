from django.apps import AppConfig


class AppFormManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_form_management'
    verbose_name = '表单管理'

    def ready(self):
        from . import signals

        from django.urls import reverse
        from app_workflow.utils import related_object_router
        from .models import FormSubmission

        related_object_router.register(
            FormSubmission,
            url_resolver=lambda obj: reverse('form_submission_detail', kwargs={'pk': obj.pk}),
            display_name_resolver=lambda obj: obj.template.name,
            person_resolver=lambda obj: obj.submitted_by,
        )

        # 注册 FormSubmission 到统一附件系统
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from .mixins import FormManagementAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=FormSubmission,
            access_mixin=FormManagementAccessMixin,
            view_permission='app_form_management.view_formsubmission',
            add_permission='app_form_management.add_formsubmission',
            delete_permission='app_form_management.delete_formsubmission',
            categories=[('OTHER', '表单附件')],
            folder_id_resolver=lambda obj: str(obj.pk),
        ))
