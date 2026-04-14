# 核心材料库与集成中心 (app_material)

## 1. 模块定位
`app_material` 是整个系统的“数据心脏”。它负责管理所有改性材料的基础档案、物性指标、应用场景和特征属性。此外，它还承担着向外部系统（如产品电子手册）提供实时 API 数据和异步 Webhook 推送的核心职责。

## 2. 核心架构说明
模块采用了 **“三层分离”** 的架构设计：
- **api/**: 基于 Django REST Framework 开放的只读接口，供外部系统查询物料。
- **integration/**: 集成逻辑层。包含 Webhook 任务的构造 (`signals.py`) 和发送 (`webhooks.py`)。
- **models/**: 结构化模型层。定义了物料、分类、场景、特征及异步任务表。

## 3. Webhook 异步任务体系
为了保证系统性能，数据同步采用 **“异步队列”** 模式：
1. **监听**: 通过 Django Signals 监听物料或维度数据的任何变动。
2. **入队**: 变动瞬间产生一条 `WebhookTask` 记录，状态为 `PENDING`。
3. **处理**: 由后台进程执行发送，成功后标记为 `SUCCESS`，失败则按指数退避原则重试。

### 运维指令
在生产环境下，必须启动任务处理器进程：
```bash
python manage.py process_webhooks
```

## 4. API 开放规范
所有外部调用必须在 Header 中携带安全 Token：
- **Header**: `X-Internal-Api-Token: catalog-portal-secure-token-2024`
- **主要端点**:
    - `/api/material/materials/`: 全量物料及过滤搜索。
    - `/api/material/scenarios/`: 应用场景列表。
    - `/api/material/characteristics/`: 材料特征列表。

## 5. 安全与权限
- **Token 校验**: 由 `InternalApiTokenPermission` 权限类控制。
- **Webhook 签名**: 推送请求携带 `X-Webhook-Secret` 签名头，接收端需验证此签名。

## 6. 扩展指南
若需增加新的同步事件（如同步到 ERP 系统）：
1. 在 `integration/signals.py` 中增加对应的信号监听。
2. 在 `integration/webhooks.py` 中定义新的推送 Payload 构造逻辑。
3. 确保目标系统的地址已在 `settings.py` 中配置。

---
**SUNWILL 材料数据中心 - 技术指南**
