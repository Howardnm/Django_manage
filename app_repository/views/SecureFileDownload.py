from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, FileResponse
from django.views import View
from django.core.exceptions import PermissionDenied
from app_project.mixins import ProjectPermissionMixin

# ==========================================
# 10. 通用下载接口
# ==========================================
class SecureFileDownloadView(LoginRequiredMixin, ProjectPermissionMixin, View):
    """
    通用安全文件下载视图
    URL格式: /repository/download/<app_label>/<model_name>/<pk>/<field_name>/
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
        self.check_download_permission(obj, model_name)

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

    def check_download_permission(self, obj, model_name):
        """
        根据模型类型执行不同的权限检查策略
        """
        user = self.request.user
        if user.is_superuser:
            return True

        # 策略 A: 项目相关文件 (ProjectFile)
        # 必须检查用户是否属于该项目组
        if model_name.lower() == 'projectfile':
            # obj 是 ProjectFile 实例
            # 路径: ProjectFile -> ProjectRepository -> Project
            project = obj.repository.project
            self.check_project_permission(project) # 使用 Mixin 检查
            return True

        # 策略 B: 材料库文件 (MaterialLibrary, MaterialFile)
        # 假设材料库对所有登录用户开放，或者检查是否有 'app_repository.view_materiallibrary' 权限
        elif model_name.lower() in ['materiallibrary', 'materialfile']:
            # 简单策略：只要登录就能看 (LoginRequiredMixin 已保证)
            # 进阶策略：检查权限
            # if not user.has_perm('app_repository.view_materiallibrary'):
            #     raise PermissionDenied("您没有查看材料库的权限")
            return True
        
        # 策略 D: 工艺库文件 (ScrewCombination)
        # 假设工艺库对所有登录用户开放
        elif model_name.lower() == 'screwcombination':
            return True
            
        # 策略 E: 原材料库文件 (RawMaterial)
        # 假设原材料库对所有登录用户开放
        elif model_name.lower() == 'rawmaterial':
            return True

        # 策略 C: 其他未知模型
        # 默认拒绝，防止意外暴露其他敏感数据
        else:
            raise PermissionDenied(f"未配置模型 {model_name} 的下载权限策略")
