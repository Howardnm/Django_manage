from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, FileResponse
from django.views import View
from django.core.exceptions import PermissionDenied
from app_project.mixins import ProjectPermissionMixin

# ==========================================
# 通用安全文件下载接口
# ==========================================
class SecureFileDownloadView(LoginRequiredMixin, View):
    """
    通用安全文件下载视图
    URL格式: /download/<app_label>/<model_name>/<pk>/<field_name>/
    """

    def get(self, request, app_label, model_name, pk, field_name):
        # 1. 直接动态获取模型 (移除所有别名映射)
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            raise Http404("模型不存在")

        # 2. 获取对象
        try:
            obj = model.objects.get(pk=pk)
        except model.DoesNotExist:
            raise Http404("文件记录不存在")

        # 3. 动态权限检查
        self.check_download_permission(obj, model_name, app_label)

        # 4. 获取文件字段
        if not hasattr(obj, field_name):
            raise Http404("字段不存在")

        file_field = getattr(obj, field_name)

        # 5. 检查文件是否存在
        if not file_field:
            raise Http404("未上传文件")

        try:
            # 6. 返回文件流
            response = FileResponse(file_field.open('rb'), as_attachment=False)
            return response
        except FileNotFoundError:
            raise Http404("物理文件丢失")

    def check_download_permission(self, obj, model_name, app_label):
        """
        根据模型类型执行严格的权限检查策略
        """
        user = self.request.user
        if user.is_superuser:
            return True

        model_name_lower = model_name.lower()

        # 策略 A: 项目专属文件 (ProjectFile)
        if model_name_lower == 'projectfile':
            project = obj.repository.project
            mixin = ProjectPermissionMixin()
            mixin.request = self.request
            mixin.check_project_permission(project) 
            return True

        # 策略 B: 材料库相关文件 (MaterialLibrary, MaterialFile)
        # 仅检查 app_material 权限
        elif model_name_lower in ['materiallibrary', 'materialfile']:
            if not user.has_perm('app_material.view_materiallibrary'):
                raise PermissionDenied("您没有访问公共材料库的权限")
            return True
        
        # 策略 C: 工艺库文件
        elif model_name_lower == 'screwcombination':
            if not user.has_perm('app_process.view_screwcombination'):
                raise PermissionDenied("您没有访问工艺库的权限")
            return True
            
        # 策略 D: 原材料库文件
        elif model_name_lower == 'rawmaterial':
            if not user.has_perm('app_raw_material.view_rawmaterial'):
                raise PermissionDenied("您没有访问原材料库的权限")
            return True
            
        # 策略 E: 预研项目文件
        elif model_name_lower == 'researchprojectfile':
            if not user.has_perm('app_basic_research.view_researchproject'):
                raise PermissionDenied("您没有访问预研项目的权限")
            return True
            
        # 策略 F: 配方库文件
        elif model_name_lower == 'formulatestresult':
            if not user.has_perm('app_formula.view_labformula'):
                raise PermissionDenied("您没有访问实验配方库的权限")
            return True

        else:
            raise PermissionDenied(f"模型 {model_name} 的权限策略未配置，访问被拒绝。")
