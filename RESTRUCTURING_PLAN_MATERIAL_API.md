# app_material API 模块解耦重构计划

## 1. 目标概述
将 `app_material` 模块中的所有 API 逻辑（Serializers, API Views, API URLs）抽离，成立一个专门的 `app_material_api` 模块。实现业务后台逻辑与外部数据服务逻辑的物理隔离。

## 2. 核心架构设计

### 2.1 模块职责划分
- **app_material (核心业务层)**: 负责数据库模型定义、Admin 后台管理、内部业务视图 (Create/Edit)、信号发送等。
- **app_material_api (服务层)**: 负责对外提供数据接口、API 版本控制、分布式验证逻辑、集成中心 (Webhook 发送任务)。

### 2.2 目录结构预想
```
app_material_api/
├── serializers/        # 所有的序列化器
├── views/              # 所有的 API ViewSets 和 APIViews
├── integration/        # Webhook 发送与集成中心
├── urls.py             # API 专用路由
└── apps.py
```

## 3. 重构步骤

### 第一阶段：初始化与基础迁移
1. 创建新应用: `python manage.py startapp app_material_api`。
2. 迁移序列化器: 将 `app_material/api/serializers.py` 移动到新模块。
3. 迁移 API 视图: 将 `app_material/api/views.py` 移动到新模块。
4. 修复导入路径: 全局更新从 `app_material.api` 到 `app_material_api` 的引用。

### 第二阶段：集成中心迁移 (Integration Hub)
1. 将 `integration/` 文件夹整体从 `app_material` 迁移至 `app_material_api`。
2. **信号重连**: 更新 `app_material/signals.py`，调用新模块中的 Webhook 推送函数。
3. **API 统一管理**: 所有分布式身份校验 (`auth/verify`) 和行为回流 (`auth/feedback`) 的 API 均由新模块管控。

### 第三阶段：路由与配置适配
1. 在 `Django_manage/urls.py` 中更新路由挂载点。
2. 在 `settings.py` 中注册新应用。
3. 清理 `app_material` 模块下的 `api/` 冗余目录。

## 4. 带来的好处
- **安全性**: 方便为 API 模块统一配置中间件（如频率限制、审计日志）。
- **专业性**: 符合 DDD（领域驱动设计）思想，外部系统对接时只需关注 `app_material_api`。
- **可维护性**: 解决目前 `app_material` 模块过于臃肿的问题，代码职责一目了然。

## 5. 迁移后 URL 结构
- 门户 API: `/api/materials/`
- 会员验证: `/api/auth/verify/`
- 行为回流: `/api/auth/feedback/`

---
**SUNWILL 架构重构小组 - 2024**
