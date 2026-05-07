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
