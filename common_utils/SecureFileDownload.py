from django.apps import apps
from django.http import Http404, FileResponse
from django.views import View
from django.core.exceptions import PermissionDenied

from app_user.mixins import UnifiedAccessMixin
from app_project.mixins import ProjectAccessMixin
from app_formula.mixins import FormulaAccessMixin
from app_process.mixins import ProcessAccessMixin
from app_raw_material.mixins import RawMaterialAccessMixin
from app_basic_research.mixins import BasicResearchAccessMixin
from app_material.mixins import MaterialAccessMixin


# ==========================================
# 通用安全文件下载接口
# ==========================================
class SecureFileDownloadView(UnifiedAccessMixin, View):
    """
    通用安全文件下载视图。
    继承 UnifiedAccessMixin，自动执行 4D 权限校验。
    """
    
    # 下载接口默认由各模块细分策略决定，此处仅需登录
    enforce_dept_isolation = False

    def get(self, request, app_label, model_name, pk, field_name):
        # 1. 动态获取模型
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            raise Http404("模型不存在")

        # 2. 获取对象
        try:
            obj = model.objects.get(pk=pk)
        except model.DoesNotExist:
            raise Http404("记录不存在")

        # 3. 核心：执行 4D 安全检查
        self.check_download_permission(obj, model_name, app_label)

        # 4. 获取文件字段并返回
        if not hasattr(obj, field_name):
            raise Http404("字段不存在")

        file_field = getattr(obj, field_name)

        # 5. 检查文件是否存在
        if not file_field:
            raise Http404("未上传文件")

        try:
            return FileResponse(file_field.open('rb'), as_attachment=False)
        except FileNotFoundError:
            raise Http404("物理文件丢失")

    def check_download_permission(self, obj, model_name, app_label):
        """
        利用各模块已有的低代码 Mixin 执行针对性校验
        """
        user = self.request.user
        if user.is_superuser:
            return True

        model_name_lower = model_name.lower()

        # 策略 A: 项目文件 (ProjectFile) -> 使用 ProjectAccessMixin 穿透检查
        if model_name_lower == 'projectfile':
            mixin = ProjectAccessMixin()
            mixin.request = self.request
            mixin.check_object_permission(obj.repository.project)
            return True

        # 策略 B: 预研项目 (ResearchProjectFile)
        elif model_name_lower == 'researchprojectfile':
            mixin = BasicResearchAccessMixin()
            mixin.request = self.request
            mixin.check_object_permission(obj.project)
            return True

        # 策略 C: 实验配方相关
        elif model_name_lower in ['formulatestresult', 'labformula']:
            mixin = FormulaAccessMixin()
            mixin.request = self.request
            # 找到对应的 LabFormula 对象
            formula = obj if model_name_lower == 'labformula' else obj.formula
            mixin.check_object_permission(formula)
            return True

        # 策略 D: 公共/共享资源 (材料库、原材料库、工艺机台)
        elif model_name_lower in ['materiallibrary', 'materialfile', 'rawmaterial', 'machinemodel', 'screwcombination']:
            # 只要有相应的查看权限即可下载 (遵循各模块 AccessMixin 的 identity_required)
            perms_map = {
                'materiallibrary': 'app_material.view_materiallibrary',
                'materialfile': 'app_material.view_materiallibrary',
                'rawmaterial': 'app_raw_material.view_rawmaterial',
                'machinemodel': 'app_process.view_machinemodel',
                'screwcombination': 'app_process.view_screwcombination',
            }
            required_perm = perms_map.get(model_name_lower)
            if required_perm and not user.has_perm(required_perm):
                raise PermissionDenied("您的权限组无权下载此公共资源文件")
            return True

        else:
            raise PermissionDenied(f"未定义的下载安全策略: {model_name}")
