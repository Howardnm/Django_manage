from django.apps import AppConfig


class AppBasicResearchConfig(AppConfig):
    name = 'app_basic_research'
    verbose_name = '基础预研项目'

    def ready(self):
        import app_basic_research.utils.signals

        # 注册自动补全
        from common_utils.autocomplete_registry import register_autocomplete
        from app_basic_research.models import ResearchProject
        from django.db.models import Q

        register_autocomplete('research_project',
            lambda q: ResearchProject.objects.filter(
                Q(code__icontains=q) | Q(name__icontains=q)),
            lambda r: {'value': r.pk, 'text': f'{r.code} {r.name}'},
        )

        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_basic_research.models import ResearchProject
        from app_basic_research.mixins import BasicResearchAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=ResearchProject,
            access_mixin=BasicResearchAccessMixin,
            view_permission='app_basic_research.view_researchproject',
            add_permission='app_basic_research.change_researchproject',
            delete_permission='app_basic_research.change_researchproject',
            categories=[
                ('REPORT', '研究报告'),
                ('DATA', '实验数据'),
                ('LITERATURE', '参考文献'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda p: str(p.pk),
        ))