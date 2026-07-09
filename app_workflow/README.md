# app_workflow — 审批工作流模块

## 目录

1. [架构概览](#1-架构概览)
2. [数据模型](#2-数据模型)
3. [审批人解析机制](#3-审批人解析机制)
4. [组织角色系统](#4-组织角色系统)
5. [BPMN 工作流引擎](#5-bpmn-工作流引擎)
6. [功能清单与操作说明](#6-功能清单与操作说明)
7. [信号与回调](#7-信号与回调)
8. [URL 端点](#8-url-端点)
9. [Admin 管理界面](#9-admin-管理界面)
10. [常见配置场景](#10-常见配置场景)

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Django Admin                              │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │ WorkflowDef  │  │ WorkflowTask     │  │ WorkflowTaskConfig │  │
│  │ BPMN XML编辑  │  │ 任务状态/指派     │  │ task_id注册/绑定    │  │
│  └──────────────┘  └─────────────────┘  └────────────────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │ OrgRole      │  │ OrgRoleAssign    │  │ 组织架构总览(矩阵)   │  │
│  │ 角色定义      │  │ 角色→用户指派    │  │ 可视化指派关系       │  │
│  └──────────────┘  └─────────────────┘  └────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BPMN 工作流引擎                                 │
│                                                                   │
│  WorkflowEngine (SpiffWorkflow 3.1.2 封装)                        │
│  ├── create_workflow()  解析 BPMN XML → BpmnWorkflow              │
│  ├── complete()         执行审批 → do_engine_steps() 推进流程      │
│  ├── return_to_task()   回退到前序 BPMN 节点                       │
│  ├── resolve_assignee() 6级优先级审批人解析链                       │
│  └── parse_camunda_assignments() 解析 BPMN camunda 扩展属性        │
│                                                                   │
│  OrgRoleResolver (组织角色解析器)                                   │
│  └── resolve(role_code) 按发起人组织归属 + 逐级回退查找审批人        │
└──────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    服务编排层                                      │
│                                                                   │
│  WorkflowService                                                  │
│  ├── start()           创建实例 + 同步任务 + 发送信号               │
│  ├── restart()         重新发起已结束的流程                         │
│  ├── complete_task()   引擎推进 + DB更新 + 信号 + 业务回调          │
│  ├── return_task()     退回到前序节点 或 发起人                     │
│  ├── claim()           候选人签收任务                               │
│  ├── reassign()        转交任务给其他人                             │
│  └── sync_tasks()      Spiff任务 → Django WorkflowTask 同步       │
└──────────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|---|---|
| BPMN 引擎 | SpiffWorkflow 3.1.2 (Python) |
| BPMN 编辑器 | bpmn-js 18.15.0 (JavaScript) |
| 扩展命名空间 | Camunda Extension (`http://camunda.org/schema/1.0/bpmn`) |
| 前端框架 | Vue 3.5 + Element Plus 2.13 |
| 后端框架 | Django 6.0 |

---

## 2. 数据模型

### 2.1 WorkflowDefinition — 流程定义

存储 BPMN 2.0 XML 配置。

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | CharField(100) | 流程名称 |
| `description` | TextField | 流程描述 |
| `bpmn_xml` | TextField | BPMN 2.0 XML 内容 |
| `is_active` | BooleanField | 是否启用 |
| `created_by` | FK → User | 创建者 |
| `created_at` / `updated_at` | DateTimeField | 时间戳 |

属性 `is_executable_bpmn`：正则检测 XML 中是否包含 `isExecutable="true"` 的 process 标签。

### 2.2 WorkflowInstance — 流程实例

运行中的工作流。

| 字段 | 类型 | 说明 |
|---|---|---|
| `definition` | FK → WorkflowDefinition | 所属流程定义 |
| `status` | CharField | RUNNING / COMPLETED / REJECTED / CANCELED |
| `context_data` | JSONField | 流程变量（含 assignee_map 等） |
| `spiff_workflow_data` | JSONField | SpiffWorkflow 序列化状态（恢复流程进度） |
| `callback_config` | JSONField | 业务回调配置 `{handler, args}` |
| `content_type` / `object_id` | GFK | 关联业务对象（FormSubmission、ProjectNode 等） |
| `started_by` | FK → User | 发起人 |
| `canceled_by` | FK → User | 取消人 |
| `cancel_reason` | TextField | 取消原因 |

### 2.3 WorkflowTask — 流程任务

单个审批节点的待办事项。

| 字段 | 类型 | 说明 |
|---|---|---|
| `instance` | FK → WorkflowInstance | 所属实例 |
| `task_name` | CharField(100) | 任务名称 |
| `assigned_to` | FK → User (nullable) | 负责人（空=待签收） |
| `candidate_users` | M2M → User | 候选用户 |
| `candidate_groups` | JSONField | 候选组名列表 |
| `status` | CharField | PENDING / COMPLETED / REJECTED / RETURNED / CANCELED |
| `form_step` | PositiveSmallIntegerField | 表单步骤号（来自 camunda:formStep） |
| `spiff_task_id` | CharField(100) | BPMN 元素 ID |
| `spiff_instance_id` | CharField(100) | Spiff 内部任务实例 ID |
| `due_date` | DateTimeField | 截止日期 |
| `remark` | TextField | 审批备注 |

### 2.4 ApprovalHistory — 审批历史

| 字段 | 类型 | 说明 |
|---|---|---|
| `instance` | FK → WorkflowInstance | 所属实例 |
| `task` | FK → WorkflowTask | 关联任务 |
| `return_target_task` | FK → WorkflowTask | 退回目标任务 |
| `approver` | FK → User | 操作人 |
| `action` | CharField | START / APPROVE / REJECT / RETURN / CANCEL |
| `remark` | TextField | 操作备注 |
| `timestamp` | DateTimeField | 操作时间 |

### 2.5 WorkflowTaskConfig — Task 节点配置

BPMN userTask 注册表，关联 task_id 与审批策略。

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | CharField(100) unique | ★ 可自由编辑。对应 BPMN userTask 的 id 属性 |
| `display_name` | CharField(100) | 如"组长审批" |
| `resolution_mode` | CharField | assignee_map / org_role / static_group / static_user |
| `org_role` | FK → OrgRole | org_role 模式绑定的组织角色 |
| `review_group` | FK → ReviewGroup | static_group 模式绑定的审核组 |
| `static_assignee` | FK → User | static_user 模式的固定审批人 |
| `workflow_definitions` | M2M → WorkflowDefinition | 所属流程定义（可选） |
| `is_active` | BooleanField | 启用状态 |

### 2.6 OrgRole — 组织角色 (app_user)

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | CharField(50) unique | 角色编码，如 `group_leader` |
| `name` | CharField(50) | 角色名称，如"组长" |
| `scope` | CharField | workgroup / department / subsidiary |
| `allow_escalation` | BooleanField | 是否允许逐级向上回退 |
| `description` | TextField | 描述 |

### 2.7 OrgRoleAssignment — 组织角色指派 (app_user)

| 字段 | 类型 | 说明 |
|---|---|---|
| `role` | FK → OrgRole | 组织角色 |
| `user` | FK → User | 被指派的用户 |
| `subsidiary` | FK → Subsidiary (nullable) | 子公司级作用域 |
| `department` | FK → Department (nullable) | 部门级作用域 |
| `workgroup` | FK → WorkGroup (nullable) | 工作组级作用域 |
| `is_primary` | BooleanField | 是否为主负责人 |

---

## 3. 审批人解析机制

`WorkflowEngine.resolve_assignee()` 按照以下优先级链依次尝试，命中后立即返回：

```
优先级      步骤                    说明
───────    ──────────────────────  ─────────────────────────────────
  ⓪       parse_camunda_assign   提前解析 BPMN camunda 属性并缓存
           ments()                （供 sync_tasks 读取 form_step 等字段）

  ①       assignee_map            代码层在启动流程时通过 context_data
                                   传入 {task_id: user_pk} 映射。
                                   优先级最高，命中后跳过后面的所有检查。

  ②       WorkflowTaskConfig      查 Admin 中注册的 task_id 配置：
           ├─ org_role           → OrgRoleResolver 自动查找
           ├─ static_user        → static_assignee 直接指派
           └─ static_group       → review_group 候选池

  ③       BPMN camunda 属性       从 BPMN XML 解析：
           ├─ camunda:assignee   → 按用户名直接指派
           ├─ camunda:candidate   → 候选用户列表
           │  Users
           └─ camunda:candidate   → 候选组（匹配 ReviewGroup）
              Groups

  ④       单人候选自动指派         恰好 1 个 candidate_users +
                                   0 个 candidate_groups → 自动指派

  ⑤       兜底：流程发起人         以上全部未命中 → 指派给 instance.started_by
```

### 解析模式对比

| 模式 | 配置位置 | 指派方式 | 依赖组织架构 | 适用场景 |
|---|---|---|---|---|
| assignee_map | 代码层 | 直接指派 | 否 | 业务代码动态计算审批人 |
| org_role ★ | Admin | 直接指派 | **是** | 按发起人层级自动匹配 |
| static_user | Admin | 直接指派 | 否 | 永远固定的审批人 |
| static_group | Admin | 候选池→签收 | 半依赖(ReviewGroup) | 固定审核组 |
| camunda:assignee | BPMN XML | 直接指派 | 否 | 快速原型/简单流程 |

---

## 4. 组织角色系统

### 4.1 解析流程

```
发起人 (张三)
  ├── subsidiary  = 上海总部
  ├── department  = 研发中心
  └── work_groups = [配方组]

审批节点 task_id="Task_leader"
  ↓
WorkflowTaskConfig(task_id="Task_leader")
  → resolution_mode = 'org_role'
  → org_role = OrgRole(code='group_leader', scope='workgroup')
  ↓
OrgRoleResolver(initiator=张三).resolve('group_leader')
  ↓
① 查 OrgRoleAssignment(role=group_leader, workgroup=配方组)
   → 李组长 ✅
   (如未找到，走回退逻辑 ↓)
  ↓
② (allow_escalation=True) 回退到部门级
   查 OrgRoleAssignment(role=group_leader, department=研发中心)
   → 张经理（如果部门经理兼任组长审批）
  ↓
③ (仍未找到) 回退到子公司级
   查 OrgRoleAssignment(role=group_leader, subsidiary=上海总部)
   → 王总
  ↓
④ 全部未找到 → 返回 None → 走后续 fallback (camunda 属性 → 发起人兜底)
```

### 4.2 回退链路

`OrgRole.allow_escalation` 控制是否启用逐级向上回退：

```
allow_escalation = True:

  scope = workgroup  →  查工作组 → 无 → 查部门 → 无 → 查子公司 → 无 → None
  scope = department →            查部门 → 无 → 查子公司 → 无 → None
  scope = subsidiary →                      查子公司 → 无 → None

allow_escalation = False:

  scope = workgroup  →  查工作组 → 无 → None (不向上查)
  scope = department →  查部门   → 无 → None
  scope = subsidiary →  查子公司 → 无 → None
```

---

## 5. BPMN 工作流引擎

### 5.1 支持的 BPMN 元素

| 元素 | 支持情况 |
|---|---|
| StartEvent / EndEvent | ✅ 完整支持 |
| UserTask | ✅ 完整支持（审批节点） |
| parallelGateway (fork/join) | ✅ 完整支持（并行审批） |
| exclusiveGateway | ✅ 完整支持（条件分支，条件表达式为 Python 风格） |
| inclusiveGateway / eventBasedGateway | ⚠️ SpiffWorkflow 原生支持，前端可视化中显示 |
| ServiceTask / ScriptTask | ❌ 未实现 |

### 5.2 Camunda 扩展属性

所有 Camunda 属性通过命名空间 `http://camunda.org/schema/1.0/bpmn` 定义在 BPMN XML 中：

| 属性 | 用途 | 示例 |
|---|---|---|
| `camunda:assignee` | 直接指派审批人（用户名） | `camunda:assignee="rnd_dir"` |
| `camunda:candidateUsers` | 候选用户列表（逗号分隔） | `camunda:candidateUsers="user1,user2"` |
| `camunda:candidateGroups` | 候选组列表（匹配 ReviewGroup.name） | `camunda:candidateGroups="dept_manager"` |
| `camunda:formStep` | 表单步骤号（用于分步填写） | `camunda:formStep="2"` |
| `camunda:formStepLabel` | 表单步骤标签 | `camunda:formStepLabel="部门审核"` |

### 5.3 条件表达式

SpiffWorkflow 原生支持 `conditionExpression`，使用 Python 风格表达式：

```xml
<bpmn:exclusiveGateway id="Gateway_decision" name="审批结果">
  <bpmn:incoming>Flow_to_gateway</bpmn:incoming>
  <bpmn:outgoing>Flow_approved</bpmn:outgoing>
  <bpmn:outgoing>Flow_rejected</bpmn:outgoing>
</bpmn:exclusiveGateway>

<bpmn:sequenceFlow id="Flow_approved" sourceRef="Gateway_decision" targetRef="EndEvent_approved">
  <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">
    Task_xxx_action == 'APPROVE'
  </bpmn:conditionExpression>
</bpmn:sequenceFlow>
```

条件表达式中的变量来自 `workflow.data`。引擎在任务完成时自动写入 `{bpmn_id}_action` 和 `{task_name}_action` 变量。

### 5.4 生命周期

```
创建 WorkflowDefinition (BPMN XML)
        │
        ▼
start() ───→ WorkflowInstance (RUNNING)
        │         │
        │         ├── sync_tasks() → WorkflowTask (PENDING)
        │         │         │
        │         │         ├── APPROVE → complete_task() → sync_tasks() → 下一批 task
        │         │         ├── REJECT  → instance.status=REJECTED → callback('ROLLBACK')
        │         │         ├── RETURN  → return_task() → 重置到前序节点
        │         │         └── 转交    → reassign() 给其他人
        │         │
        │         ├── cancel() → instance.status=CANCELED → callback('CANCELED')
        │         │
        │         └── 全部通过 → instance.status=COMPLETED → callback('DONE')
        │
        ▼
restart() ───→ (已结束的实例) → 重新发起，保留历史记录
```

---

## 6. 功能清单与操作说明

### 6.1 流程定义管理

#### 创建流程定义

1. 进入 Admin → 审批工作流 → 流程定义 → 新增
2. 填写流程名称和描述
3. 在 BPMN 编辑器中绘制流程图（拖拽式可视化编辑）
4. 保存

**BPMN XML 编写规范：**

- 使用组织角色模式时，userTask 只需 `id` 和 `name`，不需要 camunda 指派属性。
- `id` 需与 WorkflowTaskConfig 中的 `task_id` 保持一致。

```xml
<userTask id="Task_group_leader_approval" name="组长审批" />
<userTask id="Task_dept_manager_review" name="部门经理审批" />
```

**使用分步填写时，需额外添加 camunda 属性：**

```xml
<userTask id="Task_group_leader_approval" name="组长审批"
    camunda:formStep="1" camunda:formStepLabel="初审" />
<userTask id="Task_dept_manager_review" name="部门经理审批"
    camunda:formStep="2" camunda:formStepLabel="复核" />
```

#### 编辑 / 删除 / 启用禁用

- **编辑**：Admin → 流程定义 → 点击名称 → 修改 BPMN XML 或元数据 → 保存
- **删除**：仅当无运行中的实例时可删除
- **启用/禁用**：列表页操作列

### 6.2 组织角色配置

#### 完整配置流程（4步）

```
Step 1: Admin → App_User → 子公司/基地 → 创建子公司
        例：上海总部、广州分公司

Step 2: Admin → App_User → 组织角色 → 创建角色
        例：code="group_leader"  name="组长"  scope=工作组级  allow_escalation=✅

Step 3: Admin → App_User → 组织角色 → 点击角色 → 在下方 inline 表格中指派人员
        例：user=李XX  workgroup=配方组  is_primary=✅

Step 4: Admin → 审批工作流 → Task 节点配置 → 创建配置
        例：task_id="Task_group_leader_approval"  resolution_mode=org_role  org_role=组长
```

#### 查看组织架构总览

Admin → App_User → 组织角色 → 列表页顶部可见 "点击查看「组织架构总览」矩阵视图" 链接，或直接访问 `/admin/app_user/orgrole/org-matrix/`。

矩阵按作用域分为三个区块，清晰展示每个角色在各组织单元中的指派情况。点击已指派的用户名可直接跳转编辑。

### 6.3 启动审批流程

通过关联的业务模块（如 app_project、app_form_management）启动，一般自动触发。也可在代码中手动调用：

```python
from app_workflow.services import WorkflowService
from app_workflow.models import WorkflowDefinition

wf_def = WorkflowDefinition.objects.get(name='跨级审批')
instance = WorkflowService.start(
    definition=wf_def,
    started_by=request.user,
    related_object=some_business_object,
    context_data={...},        # 可选：传 assignee_map 等
    callback_config={          # 可选：业务回调
        'handler': 'myapp.handlers.on_workflow_done',
        'args': {'pk': 123},
    },
)
```

### 6.4 审批操作

审批人通过以下渠道处理待办：

1. **我的待办列表** (`/workflow/tasks/`)：查看所有 PENDING 任务
2. **表单提交详情页** (`/forms/submission/<pk>/`)：审批人可以看到当前步骤的字段开放编辑，底部有审批操作栏
3. **流程实例详情页** (`/workflow/instance/<pk>/`)：查看 BPMN 流程图状态，执行审批

**可选操作：**

| 操作 | 说明 | 条件 |
|---|---|---|
| 通过 (APPROVE) | 同意并推进到下一节点 | 当前审批人 |
| 驳回 (REJECT) | 拒绝，整个流程终止 | 当前审批人，需填写审批意见 |
| 退回 (RETURN) | 退回到前序审批节点或发起人 | 当前审批人，需选择退回目标 |
| 签收 (Claim) | 候选组内的用户主动认领任务 | 用户在候选组中且任务未指派 |
| 转交 (Reassign) | 将已指派的任务移交给其他人 | 当前负责人 |

### 6.5 表单分步填写

当 BPMN 中定义了 `camunda:formStep`，审批人可以只编辑当前步骤的字段：

1. BPMN XML 中为每个 userTask 设置 `camunda:formStep="N"` 和 `camunda:formStepLabel`
2. 表单模板中每个字段设置 `step` 属性
3. 审批人打开详情页 → 只有当前步骤的字段可编辑，其余只读
4. 底部步骤条高亮当前步骤，其余灰色
5. 审批通过后，当前步骤的表单数据自动合并到 FormSubmission.form_data

### 6.6 流程取消

发起人可以在流程 RUNNING 时取消：

- 流程实例详情页 → 取消按钮
- 或代码调用：`WorkflowService.cancel(instance, user, reason="...")`
- 取消后所有 PENDING 任务变为 CANCELED，触发 `workflow_completed` 信号和回调

### 6.7 流程重新发起

已结束（REJECTED/COMPLETED）的实例可以通过 `restart()` 重新发起，保留历史审批记录：

```python
WorkflowService.restart(instance, started_by, context_data={...})
```

---

## 7. 信号与回调

### 7.1 Django 信号

| 信号 | 触发时机 | 参数 |
|---|---|---|
| `workflow_started` | 流程启动 / 重新发起 | `instance` |
| `task_created` | 新任务同步到 DB | `task` |
| `task_completed` | 任务审批完成（通过或驳回） | `task`, `user`, `action` |
| `workflow_completed` | 流程结束（完成/驳回/取消） | `instance`, `status` |
| `task_returned` | 任务退回 | `task`, `user`, `target_task` |

### 7.2 业务回调

`WorkflowInstance.callback_config` 存储回调配置：

```json
{
  "handler": "app_project.workflow_handlers.handle_project_node_workflow_callback",
  "args": {"node_pk": 123}
}
```

流程状态变更时自动调用：
- COMPLETED → `handler(instance, target_status='DONE', **args)`
- REJECTED → `handler(instance, target_status='ROLLBACK', **args)`
- CANCELED → `handler(instance, target_status='CANCELED', **args)`

### 7.3 工具类

| 工具 | 说明 |
|---|---|
| `RelatedObjectRouter` | 注册业务模型的 URL/显示名/人员解析器，用于工作流详情页的"关联实体"链接 |
| `WorkflowFeatureRegistry` | 注册各业务模型的功能开关（如 `allow_return`），控制工作流行为的细粒度配置 |

---

## 8. URL 端点

| URL | 视图 | Method | 说明 |
|---|---|---|---|
| `definitions/` | WorkflowDefinitionListView | GET | 流程定义列表 |
| `editor/` | WorkflowEditorView | GET | BPMN 可视化编辑器（新建） |
| `editor/<pk>/` | WorkflowEditorView | GET | BPMN 可视化编辑器（编辑） |
| `save/` | WorkflowSaveView | POST | 保存/更新流程定义 |
| `definition/<pk>/delete/` | WorkflowDefinitionDeleteView | POST | 删除流程定义 |
| `definition/<pk>/toggle_active/` | WorkflowToggleActiveView | POST | 启用/禁用流程定义 |
| `tasks/` | MyTaskListView | GET | 我的待办列表 |
| `tasks/completed/` | CompletedTaskListView | GET | 已完成任务列表 |
| `initiated/` | InitiatedInstanceListView | GET | 我发起的流程列表 |
| `instance/<pk>/` | WorkflowInstanceDetailView | GET/POST | 流程实例详情 + 审批操作 |
| `instance/<pk>/cancel/` | WorkflowCancelView | POST | 取消流程 |
| `task/<pk>/claim/` | TaskClaimView | POST | 签收候选任务 |
| `task/<pk>/reassign/` | TaskReassignView | POST | 转交任务 |
| `task/<pk>/return/` | TaskReturnView | POST | 退回任务 |

---

## 9. Admin 管理界面

所有模型均注册到 Django Admin，可在侧边栏直接访问。

### 9.1 审批工作流 (app_workflow)

| 菜单项 | 说明 | 关键功能 |
|---|---|---|
| 流程定义 | BPMN 流程管理 | 创建/编辑/删除/启用禁用 |
| 流程实例 | 运行中流程 | 查看状态、关联对象 |
| 流程任务 | 任务管理 | 查看指派、状态 |
| 审批历史 | 操作日志 | 查看所有审批操作 |
| **Task 节点配置** | ★ task_id 注册表 | 所有字段可自由编辑。关联 task_id 与审批策略 |

### 9.2 Task 节点配置 Admin 操作步骤

```
Step 1/3 — 节点标识
  task_id:   自行命名（如 Task_group_leader_approval）
             需与 BPMN XML userTask 的 id 属性一致
  display_name: 如"组长审批"
  description:  可选说明

Step 2/3 — 审批人解析策略
  resolution_mode:  选择 ①~④ 之一
    ├─ ① 动态指派         → 需代码层传 assignee_map
    ├─ ② 按组织角色自动查找  → 选 org_role ★ 推荐
    ├─ ③ 静态候选组        → 选 review_group
    └─ ④ 静态指派用户      → 选 static_assignee

Step 3/3 — 关联与启用
  workflow_definitions:  可选，关联所属流程定义
  is_active:             取消勾选则该配置暂停生效
```

### 9.3 App_User (app_user) — 组织相关

| 菜单项 | 说明 | 关键功能 |
|---|---|---|
| 子公司/基地 | 组织层级 | 创建/编辑子公司 |
| [L4] 部门 | 组织层级 | 创建/编辑部门 |
| [L5] 工作组 | 组织层级 | 创建/编辑工作组 |
| **组织角色** | ★ 角色定义 + 指派 + 总览 | inline 指派编辑 + 矩阵视图 |
| **组织角色指派** | 角色→用户映射 | 按角色/用户搜索 |
| [审批] 审核组 | 传统候选组 | 创建/管理 ReviewGroup |

---

## 10. 常见配置场景

### 场景 A：三级审批（组长 → 部门经理 → 基地总经理）

**1. 创建组织角色：**

| code | name | scope | allow_escalation |
|---|---|---|---|
| group_leader | 组长 | workgroup | ✅ |
| dept_manager | 部门经理 | department | ✅ |
| subsidiary_gm | 基地总经理 | subsidiary | ❌ |

**2. 指派人员：**

| 角色 | 用户 | 组织单元 |
|---|---|---|
| 组长 | 李XX | 配方组 |
| 组长 | 王XX | 测试组 |
| 部门经理 | 张XX | 研发中心 |
| 基地总经理 | 刘XX | 上海总部 |

**3. 创建 Task 节点配置：**

| task_id | 解析模式 | org_role |
|---|---|---|
| Task_group_leader | org_role | 组长 |
| Task_dept_mgr | org_role | 部门经理 |
| Task_gm | org_role | 基地总经理 |

**4. BPMN XML：**

```xml
<bpmn:process id="three_level_approval" isExecutable="true">
  <bpmn:startEvent id="StartEvent">
    <bpmn:outgoing>Flow_1</bpmn:outgoing>
  </bpmn:startEvent>
  <bpmn:userTask id="Task_group_leader" name="组长审批">
    <bpmn:incoming>Flow_1</bpmn:incoming>
    <bpmn:outgoing>Flow_2</bpmn:outgoing>
  </bpmn:userTask>
  <bpmn:userTask id="Task_dept_mgr" name="部门经理审批">
    <bpmn:incoming>Flow_2</bpmn:incoming>
    <bpmn:outgoing>Flow_3</bpmn:outgoing>
  </bpmn:userTask>
  <bpmn:userTask id="Task_gm" name="基地总经理审批">
    <bpmn:incoming>Flow_3</bpmn:incoming>
    <bpmn:outgoing>Flow_end</bpmn:outgoing>
  </bpmn:userTask>
  <bpmn:endEvent id="EndEvent">
    <bpmn:incoming>Flow_end</bpmn:incoming>
  </bpmn:endEvent>
  <!-- 连线定义省略 -->
</bpmn:process>
```

人员变动时，只需在 Admin 中修改 `OrgRoleAssignment`，无需改 BPMN 或代码。

### 场景 B：固定审批人（总经理终审）

1. Admin → Task 节点配置 → 新建
2. task_id: `Task_final_approval`，显示名称: "总经理终审"
3. 解析模式: `static_user`，固定审批人: 选具体用户
4. BPMN XML: `<userTask id="Task_final_approval" name="总经理终审" />`

### 场景 C：候选组审批（法务审核）

1. Admin → [审批] 审核组 → 创建 "legal_review" 组，添加成员
2. Admin → Task 节点配置 → 新建
3. task_id: `Task_legal`，解析模式: `static_group`，候选审核组: legal_review
4. 运行时：legal_review 组内所有成员看到候选任务 → 其中一人签收处理

### 场景 D：带分步填写的审批

在场景 A 的 BPMN 基础上添加 `camunda:formStep`：

```xml
<bpmn:userTask id="Task_group_leader" name="组长审批"
    camunda:formStep="1" camunda:formStepLabel="初审" />
<bpmn:userTask id="Task_dept_mgr" name="部门经理审批"
    camunda:formStep="2" camunda:formStepLabel="复核" />
<bpmn:userTask id="Task_gm" name="基地总经理审批"
    camunda:formStep="3" camunda:formStepLabel="终审" />
```

表单模板中每个字段设置对应的 `step` 值。审批人在详情页只能编辑自己步骤的字段。

### 场景 E：并行审批（fork/join）

```xml
<bpmn:parallelGateway id="Gateway_fork" name="并行分发">
  <bpmn:incoming>Flow_from_task</bpmn:incoming>
  <bpmn:outgoing>Flow_to_A</bpmn:outgoing>
  <bpmn:outgoing>Flow_to_B</bpmn:outgoing>
</bpmn:parallelGateway>

<bpmn:userTask id="Task_review_A" name="技术审核" />
<bpmn:userTask id="Task_review_B" name="成本审核" />

<bpmn:parallelGateway id="Gateway_join" name="并行汇聚">
  <bpmn:incoming>Flow_from_A</bpmn:incoming>
  <bpmn:incoming>Flow_from_B</bpmn:incoming>
  <bpmn:outgoing>Flow_to_end</bpmn:outgoing>
</bpmn:parallelGateway>
```

两个审批节点同时激活，全部通过后才汇聚继续。每个节点的 `task_id` 都可独立配置解析模式。

### 场景 F：条件分支（审批通过/驳回）

```xml
<bpmn:exclusiveGateway id="Gateway_decision" name="审批结果">
  <bpmn:incoming>Flow_to_gateway</bpmn:incoming>
  <bpmn:outgoing>Flow_approved</bpmn:outgoing>
  <bpmn:outgoing>Flow_rejected</bpmn:outgoing>
</bpmn:exclusiveGateway>

<bpmn:sequenceFlow id="Flow_approved" sourceRef="Gateway_decision" targetRef="EndEvent_approved">
  <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">
    Task_review_action == 'APPROVE'
  </bpmn:conditionExpression>
</bpmn:sequenceFlow>

<bpmn:sequenceFlow id="Flow_rejected" sourceRef="Gateway_decision" targetRef="EndEvent_rejected">
  <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">
    Task_review_action == 'REJECT'
  </bpmn:conditionExpression>
</bpmn:sequenceFlow>
```

条件表达式使用 Python 风格，变量名格式为 `{bpmn_task_id}_action`（自动注入）。

---

## 附录：权限控制

`WorkflowAccessMixin` 继承自 `UnifiedAccessMixin`，配置为：

- `identity_required = IdentityConfig.INTERNAL_STAFF` — 所有内部用户可访问
- `enforce_dept_isolation = False` — 不启用部门隔离（审批默认跨部门）
- `enforce_group_isolation = False` — 不启用工作组隔离

## 附录：异常类

| 异常 | 说明 |
|---|---|
| `WorkflowError` | 通用工作流异常 |
| `WorkflowParseError` | BPMN XML 解析失败 |
| `TaskNotFoundError` | 未找到可执行的任务 |
| `CancelNotAllowedError` | 流程已结束，不允许取消 |
| `InvalidActionError` | 非法操作（如非本人尝试转交） |
| `ReturnNotAllowedError` | 退回操作不合法 |
