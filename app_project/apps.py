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

        related_object_router.register(
            Project,
            url_resolver=lambda obj: reverse('project_detail', kwargs={'pk': obj.pk}),
            display_name_resolver=lambda obj: obj.name,
            person_resolver=lambda obj: obj.manager,
        )
        related_object_router.register(
            ProjectNode,
            url_resolver=lambda obj: reverse('project_detail', kwargs={'pk': obj.project_id}),
            display_name_resolver=lambda obj: str(obj),
            person_resolver=lambda obj: obj.project.manager,
        )
