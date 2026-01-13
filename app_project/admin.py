from django.contrib import admin
from .models import *
# Register your models here.

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # 1. 修改表格列的展示 (显示 标题, 作者, 分类, 发布状态, 创建时间)
    list_display = ('name', 'manager', 'created_at', 'description')
    # 2. 添加右侧过滤器 (按 发布状态, 分类, 创建时间 筛选)
    list_filter = ('name', 'manager', 'created_at', 'description')
    # 3. 添加顶部搜索框 (支持按 标题 和 作者 搜索)
    search_fields = ('name', 'created_at', 'description')
    # --- 其他常用配置 (可选) ---
    # 每页显示多少条
    list_per_page = 20
    # 默认排序 (负号表示降序)
    ordering = ('-created_at',)
    # 点击哪些列可以进入编辑页面
    list_display_links = ('name',)


@admin.register(ProjectNode)
class ProjectAdmin(admin.ModelAdmin):
    # 1. 修改表格列的展示 (显示 标题, 作者, 分类, 发布状态, 创建时间)
    list_display = ('project', 'stage', 'round', 'order', 'status', 'updated_at', 'remark')
    # 2. 添加右侧过滤器 (按 发布状态, 分类, 创建时间 筛选)
    list_filter = ('project', 'stage', 'round', 'order', 'status', 'updated_at', 'remark')
    # 3. 添加顶部搜索框 (支持按 标题 和 作者 搜索)
    search_fields = ('stage', 'round', 'order', 'status', 'updated_at', 'remark')
    # --- 其他常用配置 (可选) ---
    # 每页显示多少条
    list_per_page = 20
    # 默认排序 (负号表示降序)
    ordering = ('-updated_at',)
    # 点击哪些列可以进入编辑页面
    list_display_links = ('project',)