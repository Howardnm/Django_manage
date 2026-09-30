from django.apps import AppConfig


class AppQuotationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_quotation'
    verbose_name = '产品报价'

    def ready(self):
        # 信号处理器（审批人解析）+ 通知类型（知会）
        import app_quotation.signals  # noqa: F401
        import app_quotation.notifications  # noqa: F401

        from django.db.models import Q
        from django.urls import reverse

        from app_attachment.configs import AttachmentConfig
        from app_attachment.registry import register_attachment
        from app_material.models import MaterialLibrary
        from app_workflow.utils import related_object_router, workflow_feature_registry
        from common_utils.autocomplete_registry import register_autocomplete

        from .mixins import QuotationAccessMixin
        from .models import QuotationRequest

        # 材料远程搜索专用键：全量搜索（无权限过滤）+ 下拉只显示 SAP 编码，
        # 同时带出 grade_name / 类型，供前端「选 SAP → 自动填产品名称/类型」。
        register_autocomplete(
            'material_sap',
            lambda q: MaterialLibrary.objects.select_related('category').only(
                'pk', 'sap_material_code', 'grade_name', 'category__name').filter(
                Q(sap_material_code__icontains=q) | Q(grade_name__icontains=q)),
            lambda m: {
                'value': m.pk,
                'text': m.sap_material_code or '',
                'grade_name': m.grade_name,
                'type_name': m.category.name if m.category_id else '',
            },
            # 不传 access_filter → 视图仅 LoginRequired 保护，返回全部材料
        )

        # 关联对象路由：审批流跳转回需求单详情
        related_object_router.register(
            QuotationRequest,
            url_resolver=lambda obj: reverse('quotation_detail', kwargs={'pk': obj.pk}),
            display_name_resolver=lambda obj: obj.code,
            person_resolver=lambda obj: obj.creator,
        )
        workflow_feature_registry.register(QuotationRequest, allow_return=True)

        # 附件：步骤⑬ 合同附件
        register_attachment(AttachmentConfig(
            parent_model=QuotationRequest,
            access_mixin=QuotationAccessMixin,
            view_permission='app_quotation.view_quotationrequest',
            add_permission='app_quotation.change_quotationrequest',
            delete_permission='app_quotation.change_quotationrequest',
            categories=[('CONTRACT', '合同附件')],
            folder_id_resolver=lambda obj: str(obj.pk),
        ))
