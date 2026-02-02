from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, FileResponse
from django.views import View
from django.core.exceptions import PermissionDenied
from app_project.mixins import ProjectPermissionMixin

# ==========================================
# 10. 通用下载接口
# ==========================================
class SecureFileDownloadView(LoginRequiredMixin, View):
    """
    通用安全文件下载视图
    URL格式: /download/<app_label>/<model_name>/<pk>/<field_name>/
    """

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
            raise Http404("文件记录不存在")

        # 3. 【核心修复】动态权限检查
        self.check_download_permission(obj, model_name, app_label)

        # 4. 获取文件字段
        if not hasattr(obj, field_name):
            raise Http404("字段不存在")

        file_field = getattr(obj, field_name)

        # 5. 检查文件是否存在
        if not file_field:
            raise Http404("未上传文件")

        try:
            # 6. 返回文件流 (FileResponse 会自动处理断点续传和 Content-Type)
            # as_attachment=False 表示尝试在浏览器内预览(如PDF)，True表示强制下载
            response = FileResponse(file_field.open('rb'), as_attachment=False)
            return response
        except FileNotFoundError:
            raise Http404("物理文件丢失")

    def check_download_permission(self, obj, model_name, app_label):
        """
        根据模型类型执行不同的权限检查策略
        """
        user = self.request.user
        if user.is_superuser:
            return True

        model_name_lower = model_name.lower()

        # 策略 A: 项目相关文件 (ProjectFile)
        # 必须检查用户是否属于该项目组
        if model_name_lower == 'projectfile':
            # obj 是 ProjectFile 实例
            # 路径: ProjectFile -> ProjectRepository -> Project
            project = obj.repository.project
            
            # 手动实例化 Mixin 并调用检查方法
            mixin = ProjectPermissionMixin()
            # 注入 request 对象，因为 Mixin 内部需要 self.request.user
            mixin.request = self.request
            mixin.check_project_permission(project) 
            return True

        # 策略 B: 材料库文件 (MaterialLibrary, MaterialFile)
        elif model_name_lower in ['materiallibrary', 'materialfile']:
            if not user.has_perm('app_repository.view_materiallibrary'):
                raise PermissionDenied("您没有查看材料库的权限")
            return True
        
        # 策略 D: 工艺库文件 (ScrewCombination)
        elif model_name_lower == 'screwcombination':
            if not user.has_perm('app_process.view_screwcombination'):
                raise PermissionDenied("您没有查看螺杆组合的权限")
            return True
            
        # 策略 E: 原材料库文件 (RawMaterial)
        elif model_name_lower == 'rawmaterial':
            if not user.has_perm('app_raw_material.view_rawmaterial'):
                raise PermissionDenied("您没有查看原材料的权限")
            return True
            
        # 策略 F: 预研项目文件 (ResearchProjectFile)
        elif model_name_lower == 'researchprojectfile':
            if not user.has_perm('app_basic_research.view_researchproject'):
                raise PermissionDenied("您没有查看预研项目的权限")
            return True
            
        # 策略 G: 配方库文件 (FormulaTestResult)
        elif model_name_lower == 'formulatestresult':
            if not user.has_perm('app_formula.view_labformula'):
                raise PermissionDenied("您没有查看实验配方的权限")
            return True

        # 策略 C: 其他未知模型
        # 默认拒绝，防止意外暴露其他敏感数据
        else:
            raise PermissionDenied(f"未配置模型 {model_name} 的下载权限策略")
