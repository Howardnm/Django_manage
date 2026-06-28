from django.apps import AppConfig


class AppProjectConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_project'
    verbose_name = '项目进度'

    def ready(self):
        import app_project.utils.signals

        # 注册自动补全
        from common_utils.autocomplete_registry import register_autocomplete, make_autocomplete_access_filter
        from app_project.mixins import ProjectAccessMixin
        from .models import Project
        from django.db.models import Q

        register_autocomplete('commercial_project',
            lambda q: Project.objects.only('pk', 'name').filter(name__icontains=q),
            lambda p: {'value': p.pk, 'text': p.name},
            'project_detail',
            access_filter=make_autocomplete_access_filter(ProjectAccessMixin),
        )

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

        # 注册工作流功能 — 项目节点审批不支持退回操作
        from app_workflow.utils import workflow_feature_registry
        workflow_feature_registry.register(ProjectNode, allow_return=False)
