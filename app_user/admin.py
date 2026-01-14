from django.contrib import admin
from .models import *
# Register your models here.

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    # 1. 修改表格列的展示 (显示 标题, 作者, 分类, 发布状态, 创建时间)
    list_display = ('user', 'department', 'phone')
    # 2. 添加右侧过滤器 (按 发布状态, 分类, 创建时间 筛选)
    list_filter = ('user', 'department', 'phone')
    # 3. 添加顶部搜索框 (支持按 标题 和 作者 搜索)
    search_fields = ('user', 'department', 'phone')
    # --- 其他常用配置 (可选) ---
    # 每页显示多少条
    list_per_page = 20
    # 默认排序 (负号表示降序)
    ordering = ('user',)
    # 点击哪些列可以进入编辑页面
    list_display_links = ('user',)