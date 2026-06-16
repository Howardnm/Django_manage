from django.apps import AppConfig

class AppFormulaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_formula'
    verbose_name = '配方数据库'

    def ready(self):
        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_formula.models import LabFormula, FormulaTestResult
        from app_formula.mixins import FormulaAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=LabFormula,
            access_mixin=FormulaAccessMixin,
            view_permission='app_formula.view_labformula',
            add_permission='app_formula.add_labformula',
            delete_permission='app_formula.change_labformula',
            categories=[
                ('REPORT', '测试报告'),
                ('DATA', '实验数据'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda f: str(f.pk),
        ))

        register_attachment(AttachmentConfig(
            parent_model=FormulaTestResult,
            access_mixin=FormulaAccessMixin,
            view_permission='app_formula.view_labformula',
            add_permission='app_formula.add_labformula',
            delete_permission='app_formula.change_labformula',
            categories=[
                ('REPORT', '检测报告'),
                ('OTHER', '其他文件'),
            ],
            permission_parent_chain='formula',
            folder_id_resolver=lambda t: str(t.formula.pk),
        ))
