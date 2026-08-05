from django.apps import AppConfig


class AppRepositoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_repository' # 确保这里的路径和你 settings.py 里的一致
    verbose_name = '项目档案库'

    def ready(self):
        # 导入信号，使其生效
        import app_repository.utils.signals

        # 注册工作流关联对象路由 & 功能开关
        from django.urls import reverse
        from app_workflow.utils import related_object_router, workflow_feature_registry
        from app_repository.models import ProjectRepositoryFieldChange

        related_object_router.register(
            ProjectRepositoryFieldChange,
            url_resolver=lambda obj: reverse(
                'project_detail', kwargs={'pk': obj.repository.project_id}
            ),
            display_name_resolver=lambda obj: (
                f"{obj.repository.project.name} 档案变更"
            ),
            person_resolver=lambda obj: obj.submitted_by,
        )
        workflow_feature_registry.register(
            ProjectRepositoryFieldChange, allow_return=False
        )

        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_repository.models import ProjectRepository, OEM
        from app_repository.mixins import RepositoryAccessMixin, ProjectRepositoryFileAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=ProjectRepository,
            access_mixin=ProjectRepositoryFileAccessMixin,
            view_permission='app_repository.view_projectrepository',
            add_permission='app_repository.change_projectrepository',
            delete_permission='app_repository.change_projectrepository',
            categories=[
                ('DRAWING_2D', '2D图纸'),
                ('DRAWING_3D', '3D数模'),
                ('STANDARD', '技术标准'),
                ('REPORT', '检测报告'),
                ('QUOTE', '报价商务'),
                ('OTHER', '其他资料'),
            ],
            permission_parent_chain='project',
            group_field='node_id',
            group_label='关联项目节点',
            folder_id_resolver=lambda repo: str(repo.project.pk),
            group_choices_resolver=lambda repo: [
                (f"node:{n.pk}", f"{n.get_stage_display()}"
                 + (f" (第{n.round}轮)" if n.round > 1 else ""))
                for n in repo.project.nodes.all().order_by('order')
            ],
        ))

        register_attachment(AttachmentConfig(
            parent_model=OEM,
            access_mixin=RepositoryAccessMixin,
            view_permission='app_repository.view_oem',
            add_permission='app_repository.change_oem',
            delete_permission='app_repository.change_oem',
            categories=[
                ('MATERIAL', '材料标准'),
                ('TEST', '测试标准'),
                ('QUALITY', '质量协议'),
                ('OTHER', '其他标准'),
            ],
            folder_id_resolver=lambda o: str(o.pk),
        ))