"""已废弃 — 菜单定义已迁移至 SidebarModule / SidebarSubItem DB 模型。

原 MenuModule 静态方法定义的 16 个菜单模块，已通过 data migration
写入 SidebarModule 和 SidebarSubItem 表。菜单服务现从 DB 动态读取。

如需修改菜单，请通过 Django Admin → [菜单] 侧边栏模块 进行配置。
"""
