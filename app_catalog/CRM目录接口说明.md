# 材料目录 API

供 CRM 后端拉取已发布材料，渲染企业官网。本系统只提供只读数据，不负责官网页面、会员登录和行为统计。

| 项 | 说明 |
|---|---|
| 基础路径 | `https://{host}/api/catalog/v1/` |
| 协议 | HTTPS，仅 GET |
| 数据范围 | `is_published = true` 的材料。未发布材料不会出现在导航树、列表或详情中 |
| 数据格式 | JSON，UTF-8。文件与背景图接口返回文件字节 |
| 版本 | 当前只有 v1。不带版本号的 `/api/catalog/` 不提供 |

`{host}` 由部署环境决定，文档不写具体内网地址。路径末尾的 `/` 需要保留。

版本在路径里，不在请求头。现在所有接口都在 `/api/catalog/v1/` 下，行为只有这一套。以后若有不兼容的变更，会另提供 `/api/catalog/v2/`，v1 保持不变。不带 `v1` 的旧路径不会转发到 v1。

## 认证

除浏览器预检 `OPTIONS` 外，每个请求都要带服务端密钥：

```http
Authorization: Bearer cat_...
```

密钥由本系统管理员签发，明文只在签发时出现一次。本接口不接受浏览器登录会话，也不接受其它系统的令牌。

| 情况 | HTTP | 响应 |
|---|---|---|
| 未带 `Authorization`，或不是 `Bearer` | 401 | `{"detail": "身份认证信息未提供。"}` |
| 密钥错误、已停用或已过期 | 401 | `{"detail": "无效的目录 API 密钥"}` |

密钥本身可以不设过期时间。过期与否以签发时的约定为准，调用方不需要轮换，除非管理员停用了这把密钥。

## 通用约定

### 分页

只适用于材料列表。

| 参数 | 位置 | 默认 | 说明 |
|---|---|---|---|
| `page` | 查询 | `1` | 页码，从 1 开始。超出范围返回 404 |
| `page_size` | 查询 | `20` | 每页条数，最大 `100`。超过 100 时按 100 返回；不是正整数时忽略，仍用 20 |

```json
{
  "count": 128,
  "next": "https://{host}/api/catalog/v1/materials/?page=2",
  "previous": null,
  "results": []
}
```

`next`、`previous` 没有更多页时为 `null`。

### 空值

- 文本字段没填时是空字符串 `""`，不是 `null`。例如颜色、阻燃等级、加工条件里的某一格。
- `null` 表示「没有这条数据」：没有加工条件、没有对应文档、没有背景图、物性数值为空。

### 时间与数字

- 时间是 ISO 8601，例如 `2026-11-10T08:30:00+08:00`。
- 物性里的数值（`value`、`min_value`、`max_value`）是字符串形式的小数，固定 3 位，例如 `"80.000"`。为空时是 `null`。

### 文件地址

JSON 里的文档地址和背景图地址都是本 API 的绝对 URL，要用同一把密钥再请求一次才拿到文件。响应中不会出现 `/media/` 直链。

同一材料、同一类别有多份未删除附件时：版本号大的优先；版本号相同，取上传时间更新的；仍相同，取主键更大的。已软删除的附件不参与。

后台修改材料后，接口有短暂缓存，一般数秒内更新。调用方不需要传缓存版本号。

## 推荐调用顺序

导航树和材料列表是配套的。导航树是菜单，列表是点进菜单后的牌号。

1. `GET /nav-tree/` 取场景 → 材料类型 → 材料特征，以及各级背景图地址。
2. 用节点 `id` 调 `GET /materials/`。注意参数名和树上的叫法不一样：类型节点的 `id` 传给 `category`，不是 `type`。
3. 用列表里的 `pk` 调 `GET /materials/{pk}/` 取物性、加工条件和文档地址。
4. 用详情里的文档地址，或导航树里的 `background`，再下载文件。

也可以不经过导航树，直接用 `search` 搜牌号或生产基地。

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/catalog/v1/nav-tree/` | 导航树 |
| GET | `/api/catalog/v1/materials/` | 已发布材料列表 |
| GET | `/api/catalog/v1/materials/{pk}/` | 材料详情 |
| GET | `/api/catalog/v1/materials/{pk}/download/{file_type}/` | 下载 TDS / MSDS / RoHS |
| GET | `/api/catalog/v1/background/{kind}/{pk}/` | 下载导航背景图 |

以下路径都相对于 `https://{host}`。

---

## 导航树

```http
GET /api/catalog/v1/nav-tree/
```

返回已发布材料实际用到的场景、类型和特征，并带上每个节点下的材料数量。没有任何已发布材料引用的场景、类型、特征不会出现。

没有查询参数。响应是数组，按场景名称排序。类型、特征在各自的父节点内按 `id` 升序。

### 场景节点

| 字段 | 类型 | 必有 | 含义 |
|---|---|---|---|
| `id` | 整数 | 是 | 应用场景主键。列表筛选时传给 `scenarios` |
| `name` | 字符串 | 是 | 场景名称 |
| `count` | 整数 | 是 | 该场景下的已发布材料数。一个材料挂了多个场景时，每个场景各计一次 |
| `background` | 字符串或 null | 是 | 背景图的绝对 URL。没有合格图片时为 `null` |
| `types` | 数组 | 是 | 该场景下出现过的材料类型 |

### 类型节点（`types[]`）

| 字段 | 类型 | 必有 | 含义 |
|---|---|---|---|
| `id` | 整数 | 是 | 材料类型主键。列表筛选时传给 `category` |
| `name` | 字符串 | 是 | 类型名称，例如 `PA66` |
| `count` | 整数 | 是 | 该场景下、该类型的已发布材料数 |
| `background` | 字符串或 null | 是 | 该类型的背景图绝对 URL，没有则为 `null` |
| `characteristics` | 数组 | 是 | 这些材料上出现过的特征。材料没挂特征时为空数组 |

### 特征节点（`characteristics[]`）

| 字段 | 类型 | 必有 | 含义 |
|---|---|---|---|
| `id` | 整数 | 是 | 材料特征主键。列表筛选时传给 `characteristics` |
| `name` | 字符串 | 是 | 特征名称 |
| `count` | 整数 | 是 | 该场景、该类型下，带有此特征的已发布材料数 |
| `background` | 字符串或 null | 是 | 该特征的背景图绝对 URL，没有则为 `null` |

`count` 是菜单上的数量，不是列表接口的 `count`。列表还可以再叠加搜索和分页。

### 示例

```json
[
  {
    "id": 12,
    "name": "汽车",
    "count": 2,
    "background": "https://{host}/api/catalog/v1/background/scenario/12/",
    "types": [
      {
        "id": 3,
        "name": "PA66",
        "count": 2,
        "background": null,
        "characteristics": [
          {
            "id": 8,
            "name": "耐热",
            "count": 1,
            "background": "https://{host}/api/catalog/v1/background/characteristic/8/"
          }
        ]
      }
    ]
  }
]
```

### 错误

| HTTP | 何时 |
|---|---|
| 401 | 密钥无效。见上文 |
| 200 | 没有任何已发布材料时返回 `[]`，不是 404 |

---

## 材料列表

```http
GET /api/catalog/v1/materials/
```

已发布材料的摘要，不含物性、加工条件和文档地址。默认按录入时间倒序。

### 查询参数

多个参数同时出现时是「并且」。

| 参数 | 类型 | 说明 |
|---|---|---|
| `scenarios` | 整数 | 一个应用场景 `id`，与导航树场景节点对应 |
| `category` | 整数 | 一个材料类型 `id`，与导航树类型节点对应 |
| `characteristics` | 整数，可逗号分隔 | 特征 `id`。多个时命中其中任一即可，例如 `8,9` |
| `search` | 字符串 | 牌号或生产基地的模糊搜索，忽略大小写。多个词用空格分开，需同时匹配 |
| `grade_name` | 字符串 | 牌号精确匹配。模糊搜索请用 `search` |
| `manufacturer` | 字符串 | 生产基地精确匹配。模糊搜索请用 `search` |
| `page` | 整数 | 页码 |
| `page_size` | 整数 | 每页条数，最大 100 |

点进导航「汽车 / PA66 / 耐热」时：

```http
GET /api/catalog/v1/materials/?scenarios=12&category=3&characteristics=8
```

### 响应

分页外壳见上文。`results[]` 每个元素：

| 字段 | 类型 | 必有 | 含义 |
|---|---|---|---|
| `pk` | 整数 | 是 | 材料主键。详情和下载都用它 |
| `display_name` | 字符串 | 是 | 与 `grade_name` 相同，方便直接展示 |
| `grade_name` | 字符串 | 是 | 材料牌号，全局唯一 |
| `manufacturer` | 字符串 | 是 | 生产基地。没填时为 `""` |
| `sap_material_code` | 字符串 | 是 | SAP 物料号，全局唯一 |
| `category` | 对象 | 是 | 所属材料类型，见下表 |
| `scenarios` | 数组 | 是 | 适用场景，可以是空数组 |
| `characteristics` | 数组 | 是 | 特征属性，可以是空数组 |
| `flammability` | 字符串 | 是 | 阻燃等级。可选值见枚举。没填时为 `""` |
| `material_color_name` | 字符串 | 是 | 颜色名称，例如「哑光黑」。没填时为 `""` |
| `pantone_code` | 字符串 | 是 | 潘通色号。没填时为 `""` |
| `rgb_value` | 字符串 | 是 | RGB 色值，约定为 `#RRGGBB`。没填时为 `""` |
| `description` | 字符串 | 是 | 特性描述。没填时为 `""` |
| `published_at` | 字符串 | 是 | 录入时间，不是单独的发布时间 |

`category`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 整数 | 材料类型主键 |
| `name` | 字符串 | 类型名称 |
| `classification` | 字符串 | 塑料归类，见枚举 |
| `description` | 字符串 | 类型描述。没填时为 `""` |

`scenarios[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 整数 | 场景主键 |
| `name` | 字符串 | 场景名称 |
| `requirements` | 字符串 | 场景技术要求。没填时为 `""` |

`characteristics[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 整数 | 特征主键 |
| `name` | 字符串 | 特征名称 |
| `description` | 字符串 | 特征描述。没填时为 `""` |

### 示例

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "pk": 101,
      "display_name": "PUB-1",
      "grade_name": "PUB-1",
      "manufacturer": "华东基地",
      "sap_material_code": "SAP-PUB-1",
      "category": {
        "id": 3,
        "name": "PA66",
        "classification": "ENGINEERING",
        "description": ""
      },
      "scenarios": [
        {"id": 12, "name": "汽车", "requirements": ""}
      ],
      "characteristics": [
        {"id": 8, "name": "耐热", "description": ""}
      ],
      "flammability": "V-0",
      "material_color_name": "哑光黑",
      "pantone_code": "PANTONE 19-4052",
      "rgb_value": "#1A1A1A",
      "description": "已发布",
      "published_at": "2026-11-10T08:30:00+08:00"
    }
  ]
}
```

### 错误

| HTTP | 何时 |
|---|---|
| 401 | 密钥无效 |
| 404 | `page` 超出范围 |

没有匹配的材料时仍是 200，`results` 为 `[]`。

---

## 材料详情

```http
GET /api/catalog/v1/materials/{pk}/
```

### 路径参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `pk` | 整数 | 列表返回的材料主键 |

响应包含列表中的全部字段，并增加下表。未发布或不存在的 `pk` 返回 404。

| 字段 | 类型 | 必有 | 含义 |
|---|---|---|---|
| `file_tds` | 字符串或 null | 是 | TDS 技术数据表的下载地址。没有则为 `null` |
| `file_msds` | 字符串或 null | 是 | MSDS 安全数据表的下载地址。没有则为 `null` |
| `file_rohs` | 字符串或 null | 是 | RoHS 环保报告的下载地址。没有则为 `null` |
| `grouped_properties` | 数组 | 是 | 按指标分类分组的物性。没有物性时为 `[]` |
| `processing_condition` | 对象或 null | 是 | 典型加工条件。没填时为 `null`，不是空对象 |

### 物性 `grouped_properties[]`

分组顺序与后台指标分类的排序一致。

| 字段 | 类型 | 含义 |
|---|---|---|
| `category_name` | 字符串 | 指标分类名称，例如「机械」 |
| `items` | 数组 | 该分类下的物性点 |

`items[]`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 整数 | 物性点主键 |
| `test_config` | 对象 | 测试项定义，见下表 |
| `value` | 字符串或 null | 数值结果，3 位小数字符串。非数值类型或未填时为 `null` |
| `value_text` | 字符串 | 文本结果。数值类型通常为 `""` |
| `unit` | 字符串 | 与 `test_config.unit` 相同，便于直接展示 |
| `remark` | 字符串 | 备注。没填时为 `""` |
| `min_value` | 字符串或 null | 数值下限（含），3 位小数字符串。未填为 `null` |
| `max_value` | 字符串或 null | 数值上限（含）。未填为 `null` |
| `min_value_text` | 字符串 | 文本或选择类型的下限。没填时为 `""` |
| `max_value_text` | 字符串 | 文本或选择类型的上限。没填时为 `""` |

`test_config`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 整数 | 测试项主键 |
| `name` | 字符串 | 指标中文名 |
| `name_en` | 字符串 | 英文名。没填时为 `""`，此时只展示中文 |
| `standard` | 字符串 | 测试标准，例如 `ISO 527` |
| `condition` | 字符串 | 测试条件。没填时为 `""` |
| `unit` | 字符串 | 单位，例如 `MPa`。没填时为 `""` |
| `data_type` | 字符串 | `NUMBER` 数值、`TEXT` 文本、`SELECT` 选择 |
| `order` | 整数 | 分类内的排序权重，小的在前 |

`data_type` 为 `NUMBER` 时看 `value`；为 `TEXT` 或 `SELECT` 时看 `value_text`。选择型的可选项列表不在本接口返回。

### 加工条件 `processing_condition`

每一行都是「典型值 + 范围」，值是已经填好的展示文本，例如 `220℃`、`210℃ - 230℃`。没填的格子是 `""`。

| 字段 | 含义 |
|---|---|
| `melt_temp_value` / `melt_temp_range` | 熔体温度 / 范围 |
| `barrel_rear_value` / `barrel_rear_range` | 料筒温度，后段 / 范围 |
| `barrel_center_value` / `barrel_center_range` | 料筒温度，中段 / 范围 |
| `barrel_front_value` / `barrel_front_range` | 料筒温度，前段 / 范围 |
| `mold_temp_value` / `mold_temp_range` | 模具温度 / 范围 |
| `temp_limit_value` / `temp_limit_range` | 加工温度上限 / 范围 |
| `injection_speed_value` / `injection_speed_range` | 注塑速度 / 范围 |
| `pre_dry_value` / `pre_dry_range` | 预干燥 / 范围 |

### 示例（只列出详情增量）

```json
{
  "pk": 101,
  "file_tds": "https://{host}/api/catalog/v1/materials/101/download/tds/",
  "file_msds": null,
  "file_rohs": null,
  "grouped_properties": [
    {
      "category_name": "机械",
      "items": [
        {
          "id": 900,
          "test_config": {
            "id": 40,
            "name": "拉伸强度",
            "name_en": "",
            "standard": "ISO 527",
            "condition": "",
            "unit": "MPa",
            "data_type": "NUMBER",
            "order": 0
          },
          "value": "80.000",
          "value_text": "",
          "unit": "MPa",
          "remark": "",
          "min_value": "70.000",
          "max_value": "90.000",
          "min_value_text": "",
          "max_value_text": ""
        }
      ]
    }
  ],
  "processing_condition": {
    "melt_temp_value": "220℃",
    "melt_temp_range": "210℃ - 230℃",
    "barrel_rear_value": "",
    "barrel_rear_range": "",
    "barrel_center_value": "",
    "barrel_center_range": "",
    "barrel_front_value": "",
    "barrel_front_range": "",
    "mold_temp_value": "",
    "mold_temp_range": "",
    "temp_limit_value": "",
    "temp_limit_range": "",
    "injection_speed_value": "",
    "injection_speed_range": "",
    "pre_dry_value": "",
    "pre_dry_range": ""
  }
}
```

### 错误

| HTTP | 何时 |
|---|---|
| 401 | 密钥无效 |
| 404 | `pk` 不存在，或材料未发布 |

---

## 下载文档

```http
GET /api/catalog/v1/materials/{pk}/download/{file_type}/
```

返回文件字节，不是 JSON。`Content-Disposition` 为附件（attachment）。请用详情里的 `file_tds`、`file_msds`、`file_rohs`，不要自己拼媒体目录地址。

### 路径参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `pk` | 整数 | 材料主键 |
| `file_type` | `tds`、`msds`、`rohs` | 小写。分别对应 TDS、MSDS、RoHS |

同一类别有多份文件时的选取规则见「文件地址」。

### 错误

| HTTP | 何时 |
|---|---|
| 401 | 密钥无效 |
| 404 | `file_type` 不是上述三个值；材料不存在或未发布；该类别没有未删除附件；磁盘上的文件已丢失 |

---

## 下载背景图

```http
GET /api/catalog/v1/background/{kind}/{pk}/
```

返回图片字节，内联展示（`Content-Disposition` 不是附件）。请用导航树节点上的 `background`。允许的格式是 jpg、jpeg、png、webp。

主数据存在就可以取图，不要求它此刻出现在导航树里。例如一个还没有被已发布材料使用的场景，只要传过背景图，这个地址仍然可用。

### 路径参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `kind` | `scenario`、`type`、`characteristic` | 场景、材料类型、材料特征 |
| `pk` | 整数 | 对应主数据的主键，与导航树节点 `id` 相同 |

### 错误

| HTTP | 何时 |
|---|---|
| 401 | 密钥无效 |
| 404 | `kind` 不在上述三个值中；主数据不存在；没有未删除的背景图；文件后缀不是允许的图片格式；磁盘上的文件已丢失 |

---

## 枚举

### 阻燃等级 `flammability`

`HB`、`V-2`、`V-0`、`5VB`、`5VA`。没填时是空字符串。

### 塑料归类 `category.classification`

| 值 | 含义 |
|---|---|
| `COMMODITY` | 通用塑料 |
| `ENGINEERING` | 工程塑料 |
| `SPECIAL` | 特种工程塑料 |
| `FLUORINE` | 氟塑料 |
| `ELASTOMER` | 热塑性弹性体 |
| `BIO` | 生物降解塑料 |
| `ALLOY` | 塑料合金 |
| `OTHER` | 其他 |

### 物性数据类型 `data_type`

| 值 | 含义 | 读哪个字段 |
|---|---|---|
| `NUMBER` | 数值 | `value`，范围看 `min_value` / `max_value` |
| `TEXT` | 文本 | `value_text`，范围看 `min_value_text` / `max_value_text` |
| `SELECT` | 选择 | 同文本。可选项列表不返回 |

## 错误格式

失败时响应体为：

```json
{"detail": "错误说明"}
```

本接口没有自定义业务错误码。不要依赖 `detail` 的具体措辞做分支，用 HTTP 状态码即可。

| HTTP | 含义 |
|---|---|
| 401 | 未认证或密钥无效 |
| 404 | 资源不存在、材料未发布、文件不存在，或页码超出范围 |
| 405 | 使用了 GET 以外的方法 |

## 不在本接口中的数据

以下内容不会出现在响应里，请不要向接口要：

- 材料创建人，以及任何后台账号信息
- 是否发布的标记。能查到的都是已发布材料
- TDS、MSDS、RoHS 以外的附件，例如 UL、REACH、COC、规格书
- 物性选择项的选项列表
- `/media/` 媒体目录直链
