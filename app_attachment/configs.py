"""
附件配置数据类

每个业务模块通过 AttachmentConfig 声明式注册其附件需求，
包括权限策略、文件分类、上传限制等。
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


@dataclass
class AttachmentConfig:
    """
    声明式附件配置。

    各业务模块在 apps.py ready() 中创建实例并调用
    register_attachment() 注册到全局 Registry。
    """

    # ---- 必填字段 ----

    # 父模型类（如 MaterialLibrary, ResearchProject）
    parent_model: type

    # 权限 Mixin 类（如 MaterialAccessMixin, ProjectAccessMixin）
    # 用于附件操作的 4D 权限校验
    access_mixin: type

    # Django 原生权限码
    view_permission: str    # 查看附件列表/下载附件所需的权限码
    add_permission: str     # 上传附件所需的权限码
    delete_permission: str  # 删除附件所需的权限码

    # ---- 可选字段 ----

    # 文件分类选项 [(value, label), ...]
    # 默认只有一个"其他"分类
    categories: List[Tuple[str, str]] = field(default_factory=lambda: [
        ('OTHER', '其他文件')
    ])

    # 权限穿透链：从 parent_obj 到权限承载对象的属性路径
    # 例如 ProjectFile 的父对象是 ProjectRepository，
    # 但权限检查应针对 repository.project（Project 模型）
    # 此时设置 permission_parent_chain = 'project'
    permission_parent_chain: Optional[str] = None

    # 每个父对象最大附件数（None = 不限制）
    max_attachments: Optional[int] = None

    # 是否允许上传/删除操作（模板中控制按钮显示）
    allow_upload: bool = True
    allow_delete: bool = True

    # ---- 分组字段配置 ----

    # group_key 的来源字段名，如 'node_id'，非空时启用分组功能
    group_field: Optional[str] = None

    # 上传表单中分组字段的标签
    group_label: str = '关联节点'

    # 分组选项解析器: (parent_obj) -> [(key, label), ...]
    # 用于上传弹窗中的 group_key 选项列表
    group_choices_resolver: Optional[Callable] = None

    # ---- 存储路径配置 ----

    # 文件夹 ID 解析器: (parent_obj) -> str
    # 用于 upload_file_path 确定文件存储子目录
    # 默认: str(parent_obj.pk)
    folder_id_resolver: Optional[Callable] = None
