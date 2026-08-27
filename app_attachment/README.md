# app_attachment — 统一附件管理模块

## 1. 概述

替项目中各业务模块分散的附件上传/下载/删除逻辑，提供统一的管理能力。

**核心特性**：
- **GFK 多态关联** — 一个 `Attachment` 模型支持任意业务模块作为父对象
- **声明式注册** — 业务模块在 `apps.py` 中声明配置，零代码侵入
- **4D 权限适配** — 自动继承各模块的 `UnifiedAccessMixin` 权限策略
- **UUID 下载令牌** — 每个附件独立 UUID 下载链接，防 ID 枚举
- **HTMX 开箱即用** — 上传弹窗、列表刷新全部基于 HTMX，一行模板标签即可嵌入
- **通用分组** — `group_key` 字段支持按节点/阶段/类型等任意维度分组展示
- **CAD 在线预览** — STP/STEP/IGES 在新窗口旋转查看（浏览器端 OpenCascade WASM）

---

## 2. 模块结构

```
app_attachment/
├── models.py             # Attachment 统一模型（GFK）
├── configs.py            # AttachmentConfig 声明式配置数据类
├── registry.py           # 全局注册中心（model_class → config）
├── views.py              # CRUD 视图（列表/上传/下载/预览分发/删除）
├── forms.py              # AttachmentUploadForm 通用上传表单
├── urls.py               # URL 路由（app_name='attachment'）
├── utils.py              # PermissionAdapter 权限适配器
├── storage.py            # 文件路径生成器 + FileSystemStorage Monkey-patch
├── validators.py         # validate_file_size（50MB 限制）
├── signals.py            # post_delete 物理文件清理
├── admin.py              # Django Admin 管理界面
├── apps.py               # AppConfig（加载 signals）
├── templatetags/
│   └── attachment_tags.py # {% attachment_panel %}, {% attachment_url %}
└── README.md             # 本文档
```

模板文件：`templates/apps/app_attachment/`
```
_attachment_panel.html      # 完整附件面板（卡片 + 列表 + 弹窗）
_file_list.html             # 文件列表表格（HTMX 局部刷新）
_upload_modal.html          # 上传弹窗表单
_cad_preview_button.html    # 3D 预览按钮
cad_preview.html            # CAD 全屏预览页（由 viewer 路由分发）
```

静态资源：
```
static/js/common/cad_preview.js
static/css/common/cad_preview.css
static/three/core-0.149.0/            # Three.js + OrbitControls（MIT）
static/occt-import-js/core-0.0.23/    # OpenCascade WASM（LGPL-2.1，勿合并进业务 JS）
```

---

## 3. Attachment 模型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `content_type` | FK → ContentType | 父对象类型 |
| `object_id` | PositiveIntegerField | 父对象主键 |
| `parent` | GenericForeignKey | 父对象（ContentType + object_id） |
| `file` | FileField | 文件附件（最大 50MB） |
| `display_name` | CharField(200) | 显示名称（留空自动取文件名） |
| `description` | TextField | 备注/描述 |
| `category` | CharField(30) | 文件分类（如 TDS, MSDS, DRAWING） |
| `group_key` | CharField(100) | 分组标识（如 "node:15"） |
| `version` | PositiveIntegerField | 版本号（默认 1） |
| `uploader` | FK → User | 上传人 |
| `uploaded_at` | DateTimeField | 上传时间（自动） |
| `file_size` | BigIntegerField | 文件大小（字节，自动填充） |
| `download_token` | UUIDField | 下载令牌（唯一，自动生成） |
| `is_deleted` | BooleanField | 软删除标记 |

**数据库索引**：
- `(content_type, object_id)` — 查询父对象的所有附件
- `(content_type, object_id, category)` — 按分类筛选
- `(content_type, object_id, group_key)` — 按分组筛选
- `(uploader)` — 按上传人筛选

---

## 4. 快速开始 — 为新模块注册附件功能

### 4.1 在 `apps.py` 中注册

```python
# app_your_module/apps.py
from django.apps import AppConfig

class AppYourModuleConfig(AppConfig):
    name = 'app_your_module'

    def ready(self):
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_your_module.models import YourModel
        from app_your_module.mixins import YourAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=YourModel,                          # 必填：父模型类
            access_mixin=YourAccessMixin,                    # 必填：权限 Mixin
            view_permission='app_your_module.view_yourmodel',  # 必填
            add_permission='app_your_module.change_yourmodel', # 必填
            delete_permission='app_your_module.change_yourmodel', # 必填
            categories=[                                     # 可选：文件分类
                ('REPORT', '测试报告'),
                ('DATA', '实验数据'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda obj: str(obj.pk),      # 推荐：文件夹 ID
            max_attachments=50,                               # 可选：附件上限
        ))
```

### 4.2 在详情页模板中嵌入附件面板

```django
{% load attachment_tags %}
{% attachment_panel object %}
```

一行代码即可获得完整的附件上传/下载/删除 UI。

---

## 5. 模板标签

### 5.1 `{% attachment_panel parent_obj %}`

渲染完整的附件管理面板（文件列表 + 上传按钮 + 上传弹窗）。

```django
{% load attachment_tags %}
{% attachment_panel project %}
{% attachment_panel material %}
{% attachment_panel repo %}
```

### 5.2 `{% attachment_url parent_obj 'TDS' %}`

获取指定分类第一个附件的下载链接。

```django
{% load attachment_tags %}
{% attachment_url material 'TDS' as tds_url %}
{% if tds_url %}
    <a href="{{ tds_url }}" target="_blank">下载 TDS</a>
{% endif %}
```

---

## 6. URL API

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/attachment/<ct_id>/<obj_id>/` | 附件列表（HTMX 返回 `_file_list.html`，普通请求返回 `_attachment_panel.html`） |
| GET | `/attachment/<ct_id>/<obj_id>/upload/` | 上传表单（弹窗内容） |
| POST | `/attachment/<ct_id>/<obj_id>/upload/` | 处理文件上传 |
| GET | `/attachment/download/<token>/` | 安全下载（UUID token 校验 + 权限检查） |
| GET | `/attachment/viewer/<token>/` | 通用在线预览分发（按 `preview_kind` 选模板，当前仅 cad3d） |
| POST | `/attachment/delete/<pk>/` | 软删除附件 |

**URL 名称**: `app_name = 'attachment'`

```django
{% url 'attachment:list' ct_id obj_id %}
{% url 'attachment:upload' ct_id obj_id %}
{% url 'attachment:download' token=att.download_token %}
{% url 'attachment:viewer' token=att.download_token %}
{% url 'attachment:delete' att.pk %}
```

---

## 7. AttachmentConfig 完整配置参考

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_model` | `type` | ✅ | 业务父模型类 |
| `access_mixin` | `type` | ✅ | 权限 Mixin 类 |
| `view_permission` | `str` | ✅ | 查看附件的 Django 权限码 |
| `add_permission` | `str` | ✅ | 上传附件的 Django 权限码 |
| `delete_permission` | `str` | ✅ | 删除附件的 Django 权限码 |
| `categories` | `List[Tuple]` | | 文件分类选项，默认 `[('OTHER', '其他文件')]` |
| `permission_parent_chain` | `str` | | 权限穿透链，如 `'project'` |
| `max_attachments` | `int` | | 附件数量上限，`None` = 不限 |
| `allow_upload` | `bool` | | 是否显示上传按钮，默认 `True` |
| `allow_delete` | `bool` | | 是否显示删除按钮，默认 `True` |
| `group_field` | `str` | | 分组字段名，非空时启用分组 |
| `group_label` | `str` | | 分组字段标签，默认 `'关联节点'` |
| `group_choices_resolver` | `Callable` | | 分组选项回调：`(parent) -> [(key, label)]` |
| `folder_id_resolver` | `Callable` | | 文件夹 ID 回调：`(parent) -> str` |

---

## 8. 权限系统

`PermissionAdapter` 按以下顺序执行 5 维权限检查：

| 步骤 | 维度 | 检查内容 |
|------|------|---------|
| 1 | 认证 | 未登录 → `PermissionDenied` (403) |
| 2 | 超管 | `is_superuser` → 直接放行 |
| 3 | 身份角色 | `user.user_type in mixin.identity_required` |
| 4 | 用户等级 | `user.user_level >= mixin.min_level_required` |
| 5 | Django 权限码 | `user.has_perm(config.view_permission)` |
| 6 | 对象级 | `mixin.check_object_permission(obj)` — L4 部门隔离 + L5 工作组 |

`permission_parent_chain` 示例：
- ProjectRepository 的附件：权限检查对象是 `repo.project`（Project 模型）
- FormulaTestResult 的附件：权限检查对象是 `result.formula`（LabFormula 模型）

---

## 9. 文件存储

`storage.py` 中的 `upload_file_path` 生成如下路径：

```
upload_files/<model_name>/<folder_id>/<YYYY-MM-DD>/<filename.ext>
```

- `model_name`：父对象的 model_name
- `folder_id`：由 `config.folder_id_resolver(parent)` 计算（默认 `parent.pk`）
- 文件名冲突时自动追加 `(1)`, `(2)` 数字后缀

各模块的 `folder_id` 示例：

| 模块 | folder_id | 路径示例 |
|------|-----------|---------|
| MaterialLibrary | `m.pk` | `upload_files/materiallibrary/42/2026-06-16/spec.pdf` |
| ProjectRepository | `repo.project.pk` | `upload_files/projectrepository/7/2026-06-16/drawing.dwg` |
| OEM | `o.pk` | `upload_files/oem/3/2026-06-16/standard.pdf` |

---

## 10. 安全

### 10.1 下载令牌

每个附件创建时自动生成唯一 `download_token` (UUID4)。下载时必须提供正确 token：

```
/attachment/download/550e8400-e29b-41d4-a716-446655440000/
```

- 无效 token → **403**（不区分"不存在"和"无权访问"）
- 有效 token + 无权限 → **403**
- 有效 token + 有权限 → 文件流

### 10.2 操作权限

| 操作 | 权限检查 |
|------|---------|
| 查看列表 | `config.view_permission` |
| 下载文件 | `config.view_permission` + 对象级权限 |
| 上传文件 | `config.add_permission` + 对象级权限 |
| 删除文件 | `config.delete_permission` + 对象级权限 |

### 10.3 软删除

删除操作仅设置 `is_deleted=True`，不删除数据库记录和物理文件。可配合 `django-cleanup` 实现物理文件清理。

---

## 11. 高级用法

### 11.1 按项目节点分组

```python
register_attachment(AttachmentConfig(
    parent_model=ProjectRepository,
    # ...
    group_field='node_id',
    group_label='关联项目节点',
    group_choices_resolver=lambda repo: [
        (f"node:{n.pk}", f"{n.get_stage_display()}" +
         (f" (第{n.round}轮)" if n.round > 1 else ""))
        for n in repo.project.nodes.all().order_by('order')
    ],
    folder_id_resolver=lambda repo: str(repo.project.pk),
))
```

### 11.2 View 中手动查询附件

```python
from django.contrib.contenttypes.models import ContentType
from app_attachment.models import Attachment

ct = ContentType.objects.get_for_model(my_object)
attachments = Attachment.objects.filter(
    content_type=ct,
    object_id=my_object.pk,
    is_deleted=False,
).order_by('-uploaded_at')
```

### 11.3 构建自定义分组展示页

参考 `app_repository/views/ProjectRepository.py` 中的 `ProjectFileDetailView`，展示了按 `group_key` 分组的完整模式。

---

## 12. CAD 在线预览（STP / STEP / IGES）

附件列表对 `.stp` / `.step` / `.igs` / `.iges` 显示「3D 预览」按钮，新窗口打开 viewer 页，可旋转 / 缩放 / 平移，并支持装配结构树（搜索、显隐过滤、件数统计）、六面视图与视轴旋转、正交投影、网格/轴线、线框、X 射线透视、旋转中心、XYZ 剖切、爆炸图（径向 / X / Y / Z + 等距拉开，可选零件中心）、光照和 PNG 截图。解析在浏览器 Web Worker 中完成（occt-import-js WASM），不占用 Django worker。列表页不加载 Three.js / WASM。

| 项 | 说明 |
|----|------|
| 入口 | 附件列表 / 项目资料库的预览按钮 → `target="_blank"` 打开 viewer |
| 全屏 | `GET /attachment/viewer/<token>/`（`attachment:viewer`），按 `Attachment.preview_kind` 分发模板；独立页面，不套 `base.html`（无侧栏/顶栏） |
| 权限 | 与下载相同（UUID token + 父对象 view 权限）；无权限 403 |
| 不支持的类型 | viewer 返回 **404**（例如对 PDF 打开该 URL） |
| 上限 | 上传仍为 50MB；大于 20MB 会提示解析可能较慢，复杂模型可能因 WASM 内存失败 |
| 许可证 | Three.js MIT；occt-import-js **LGPL-2.1**（独立 js/wasm 动态加载，勿合并进业务脚本） |

`preview_kind` 当前仅 `'cad3d'`。以后加 PDF / 图片预览：在模型中返回新 kind，并往 `VIEWER_TEMPLATES` 登记模板，URL 不用改。

不在范围内：DWG/DXF、量测、切口补面、服务端 tessellation。

---

## 13. 已注册模块清单

| 模块 | 父模型 | 文件夹解析 |
|------|--------|-----------|
| `app_basic_research` | `ResearchProject` | `str(p.pk)` |
| `app_formula` | `LabFormula` | `str(f.pk)` |
| `app_formula` | `FormulaTestResult` | `str(t.formula.pk)` |
| `app_material` | `MaterialLibrary` | `str(m.pk)` |
| `app_process` | `ScrewCombination` | `str(s.pk)` |
| `app_process` | `ProcessProfile` | `str(p.pk)` |
| `app_raw_material` | `RawMaterial` | `str(m.pk)` |
| `app_repository` | `ProjectRepository` | `str(repo.project.pk)` |
| `app_repository` | `OEM` | `str(o.pk)` |
| `app_trial_production` | `TestingOrder` | `str(t.pk)` |
