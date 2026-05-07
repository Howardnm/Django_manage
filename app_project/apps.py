from django.apps import AppConfig


class AppProjectConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_project'
    verbose_name = '项目进度'

    def ready(self):
        import app_project.utils.signals

        from django.urls import reverse
        from app_workflow.utils import related_object_router
        from .models import Project, ProjectNode

        related_object_router.register(Project, lambda obj: reverse('project_detail', kwargs={'pk': obj.pk}))
        related_object_router.register(ProjectNode, lambda obj: reverse('project_detail', kwargs={'pk': obj.project_id}))
