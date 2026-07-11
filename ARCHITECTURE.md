# ARCHITECTURE.md — 密教模拟器S2 在线沙盒后端

## 1. 项目目标

**密教模拟器S2** 是一个以"飞升竞赛"为核心的多人共享世界在线沙盒游戏。

本项目（`src/judge/`）是该游戏的**唯一后端服务**。当前已实现模块：

- **PvP 战斗裁判引擎**：对战管理、RPS 结算、飞书 Base 双向同步
- **Player Panel（玩家面板）**：玩家登录后的主入口，通过浏览器 HTML 页面访问

未来计划模块（不在此服务之外另建后端）：

- 背包系统、成就系统、探索系统、飞升仪式、NPC 交互等

当前项目边界：

- **已实现**：PvP 对战管理（完整生命周期）、RPS 结算引擎、资源流转、飞书 Base 同步、玩家面板（HTML+JS）、法官面板
- **未实现**：世界模拟、NPC 交互、探索系统、飞升仪式、物品管理、玩家账户

这是一个独立部署的 FastAPI 服务，负责：

- 管理 PvP 对战生命周期（创建、组牌、回合提交、结算、终止）
- 执行回合制 RPS（石头剪刀布）同时结算
- 与飞书多维表格（Base）双向同步战斗状态
- 为玩家提供 Web 面板进行选牌、出牌、战斗回顾

---

## 2. 系统整体数据流

```
┌─────────────────────────────────────────────────┐
│          飞书 Base（当前阶段玩家入口/数据层）       │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 法官面板  │ │ 选牌界面  │ │ 战斗状态/记录   │  │
│  └──────────┘ └──────────┘ └────────────────┘  │
└──────────────────┬──────────────────────────────┘
                   │ Webhook / API 回调
                   ↓
┌─────────────────────────────────────────────────┐
│           飞书 Workflow 自动化                    │
│  · 监听 Base 记录变更                             │
│  · 触发 POST /api/battle/webhook                 │
│  · 触发 POST /api/battle/confirm-from-base       │
└──────────────────┬──────────────────────────────┘
                   │ HTTP POST
                   ↓
┌─────────────────────────────────────────────────┐
│        FastAPI 战斗裁判（Render.com）             │
│  ┌───────────────────────────────────────────┐  │
│  │  Routes（HTTP 层）                         │  │
│  │  /api/battle/*  + /judge 面板              │  │
│  ├───────────────────────────────────────────┤  │
│  │  BattleManager（生命周期）                 │  │
│  ├──────────────┬────────────────────────────┤  │
│  │  Engine      │  Integration               │  │
│  │  · RPS结算   │  · feishu_client           │  │
│  │  · 资源流转  │  · base_sync               │  │
│  │  · 牌库验证  │                            │  │
│  └──────────────┴────────────────────────────┘  │
└──────────────────┬──────────────────────────────┘
                   │ 写入回合结果
                   ↓
┌─────────────────────────────────────────────────┐
│      飞书 Base（结果展示 + 下一轮入口）            │
│                                                  │
│  注：未来可增加独立 Player Client（Web/App），    │
│  直接调用本服务 REST API，替代 Base+Workflow 链路。│
│  当前架构的分层设计（Routes → Engine → Integration）│
│  已为此预留空间，不构成约束。                      │
│  · 回合记录、HP 变动、资源状态                     │
│  · 玩家查看 → 提交下一轮                          │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│        Dashboard（法官操作入口）                   │
│  /judge → judge_panel.html                      │
│  · 查看待发起对战                                 │
│  · 手动发起对战                                   │
│  · 调用 /api/battle/init-from-base               │
└─────────────────────────────────────────────────┘
```

---
### Player Panel（玩家面板 — 2026-07-15 更新）

```
┌─────────────────────────────────────────────────┐
│           Player Panel（玩家入口页面）             │
│  /player → player_client.html                   │
│                                                  │
│  输入姓名 → section-home（模块卡片）               │
│  ┌──────────────────────────────────────────┐   │
│  │  ⚔ 战斗  │  🎒 背包  │  🏆 成就          │   │
│  │  (活跃)  │  (占位)   │  (占位)           │   │
│  └──────────────────────────────────────────┘   │
│         │ 点击 ⚔                                  │
│         ▼                                        │
│  section-battle-module（战斗列表）                │
│  ┌──────────────────────────────────────────┐   │
│  │  进行中的战斗 → [进入战斗]                 │   │
│  │  历史战斗     → [查看回顾]                 │   │
│  └──────────────────────────────────────────┘   │
│         │                    │                   │
│         ▼                    ▼                   │
│  section-battle        section-replay            │
│  (选牌/对战/结束)        (只读回顾)                │
└─────────────────────────────────────────────────┘

前端 JS 模块结构:
  static/js/
    common/ui.js              ← UI.setLoading/clearLoading/showError/showToast
    player/
      state.js                ← PlayerState 全局状态对象
      player_modules.js       ← PlayerModules[] 模块注册表
      player_panel.js         ← 入口/主页/renderModules/returnToPanel
      battle_module.js        ← 战斗模块列表
      battle.js               ← 战斗仪表盘（选牌/出牌/结算）
      replay.js               ← 战斗回顾

Player Module Registry:
  所有模块在 player_modules.js 的 PlayerModules 数组中注册。
  renderModules() 动态生成模块卡片 HTML，onclick 绑定 ModuleManager.open(id, this)。
  enabled: true  → 可点击，ModuleManager 管理 enter/exit
  enabled: false → 锁定状态，无点击事件
  新增模块时只需在数组中添加条目 + 创建对应 JS 文件 + 实现 enter/exit。

Module Lifecycle:
  ModuleManager.open("battle")
    ├─ ModuleManager.close(current)   ← 调用旧模块 exit()
    └─ window[mod.enter](btn)         ← 调用新模块 enter()

Module UI State Flow:
  enter(btn)
    ├─ show section
    ├─ [loading]  LOADING_HTML  ← 立即显示，禁止显示空数据占位
    ├─ fetch API
    │   ├─ success + data  → renderData()
    │   │   ├─ data present → 渲染列表
    │   │   └─ data empty   → "暂无 XXX"
    │   └─ error            → ERROR_HTML + showError()
    └─ UI.clearLoading(btn)

**设计原则：**
- Player Panel 是玩家进入游戏后的**主入口**，Battle 只是功能模块之一
- `PlayerState` 对象是唯一共享状态容器，禁止裸全局变量
- `UI.*` 是统一交互入口，所有按钮必须通过它管理 loading 状态
- 每个 JS 文件对应一个功能模块，一个 `section-*` HTML 区域
- 未来新模块：在 `PlayerModules` 注册 + 新建 `static/js/player/<module>.js` + 新建 `section-<module>`，不修改现有文件

---
### 对战完整流程

```
1. 法官在 judge_panel.html 发起对战
      ↓ POST /api/battle/init-from-base
2. 服务器从Base「玩家」表读取双方性相等级
      ↓
3. 创建 BattleSession，返回双方可用卡牌列表
      ↓ (写入Base「玩家可用牌」表)
4. 玩家在Base「玩家战斗状态」表选8张牌
      ↓
5. 双方确认后 Workflow 触发 POST /api/battle/confirm-from-base
      ↓
6. 服务器锁定牌库，初始化 HP=20，第1回合开始
      ↓ (写入Base「对战管理」表状态)
7. [每回合] 玩家在Base选牌 → Workflow → POST /api/battle/webhook
      ↓
8. 双方都提交后 → RPS结算 → 更新HP/资源 → 写回Base
      ↓
9. HP≤0 → 战斗结束 → 写回最终结果
```

---

## 3. 目录结构说明

```
onling-battle-royale/
├── CLAUDE.md                        # 项目开发规则
├── ARCHITECTURE.md                  # 架构文档（本文件）
├── render.yaml                      # Render.com 部署配置
├── .gitignore
│
├── .claude/
│   ├── Constitution/                # 设计宪法（不直接控制代码）
│   │   ├── Project_Constitution.md  #   世界观设计原则
│   │   ├── Combat_Constitution.md   #   战斗系统设计原则
│   │   └── NPC_Design_Constitution.md
│   ├── memory/                      # 项目记忆存储
│   │   └── MEMORY.md                #   记忆索引
│   ├── settings.local.json          # 本地Claude Code设置
│   └── scheduled_tasks.json         # 定时任务
│
├── docs/
│   ├── combat/
│   │   ├── README.md                # V6战斗系统使用说明
│   │   ├── generate_cards_v6.py     # 牌组生成脚本（Excel→设计文档用）
│   │   └── 牌组/战斗牌组_v6.xlsx    # 48张卡牌数据源
│   ├── design/                      # 设计文档（世界观、地图、NPC）
│   ├── archive/                     # 历史版本归档（V2/V4/V5战斗设计）
│   └── operations/                  # 运维文档（飞书安装指南）
│
├── scripts/                         # 独立辅助脚本
│   ├── generate_items_excel.py      #   道具/搜索池生成
│   └── 道具与搜索池.xlsx
│
└── src/
    └── judge/                       # ★ 战斗裁判引擎（部署单元）
        ├── app.py                   # FastAPI 入口 & 应用工厂
        ├── requirements.txt         # Python 依赖
        │
        ├── engine/                  # 纯战斗逻辑（无HTTP依赖）
        │   ├── card_library.py      #   48张卡牌完整定义
        │   ├── deck_validator.py    #   选牌校验器（8张）
        │   ├── resource_engine.py   #   资源流转引擎（6资源）
        │   └── rps_resolver.py      #   RPS结算核心
        │
        ├── routes/                  # HTTP 路由层
        │   ├── battle.py            #   对战相关端点（7个）
        │   ├── webhook.py           #   Webhook处理器
        │   └── judge_panel.py       #   法官面板页面 + pending API
        │
        ├── integration/             # 外部服务集成
        │   ├── feishu_client.py     #   飞书 OpenAPI 客户端（HTTP）
        │   └── base_sync.py         #   战斗状态→Base 同步
        │
        ├── models/                  # Pydantic 数据模型
        │   ├── requests.py          #   请求模型
        │   └── responses.py         #   响应模型
        │
        ├── templates/               # 静态页面
        │   └── judge_panel.html     #   法官操作面板（HTML+JS）
        │
        └── tests/                   # 测试
            └── test_battle_scenarios.py  # 战斗场景测试（8个）
```

---

## 4. 核心模块说明

### 4.1 Battle Engine（`engine/`）

**纯逻辑层**，不依赖 FastAPI/HTTP/飞书。所有输入输出为 Python 对象。

#### 4.1.1 `card_library.py` — 卡牌库
- 定义 48 张卡牌的完整数据（`Card` dataclass）
- 5 种行动类别（进攻/防御/佯攻/打断/状态）
- 6 性相 + 通用（刃/蛾/铸/冬/心/灯）
- 4 个等级门槛（Lv2/Lv6/Lv10/Lv15）
- 提供查询：`get_card()`, `get_available_cards()`, `print_stats()`

#### 4.1.2 `deck_validator.py` — 组牌校验
- 计算多性相玩家的可用卡牌（并集）
- 校验 8 张组牌合法性（数量、不重复、不超门槛）
- 自动推荐8张牌（balanced/aggressive/defensive/control 策略）

#### 4.1.3 `resource_engine.py` — 资源引擎
- `BattleState`：单个玩家的完整战斗状态（HP、6资源、看破、特殊状态）
- `ResourceEngine`：资源生成/消耗/上限/衰减规则
  - 锋芒(刃)：上限3，进攻命中+1，未进攻-1
  - 幻影(蛾)：上限3，闪避/佯攻+1，无衰减
  - 蓄力(铸)：上限3，防御+1，进攻时消耗
  - 寒意(冬)：上限3，敌方debuff，3层触发处决（伤害翻倍）
  - 脉动(心)：上限4，每步+1，受伤-1
  - 洞悉(灯)：上限2，对手重复类别/防御+1
  - 看破(通用)：上限2，防御成功+1，进攻自动消耗×2/×4

#### 4.1.4 `rps_resolver.py` — RPS结算器
- 25种 RPS 交互矩阵（5×5类别）
- `resolve_round()` 完整结算一回合：
  1. RPS 交互判定（减免/绕过/取消/闪避/幻象）
  2. 伤害计算（基础伤害、连击、看破翻倍、锋芒加成、寒意削减）
  3. 寒意处决检查
  4. 应用伤害
  5. 资源变更
  6. 每步资源结算（锋芒衰减、脉动步末、洞悉检查）
  7. 特殊卡牌效果处理（40+种，如终焉后效、不屈锁血）
  8. 胜负判定（HP≤0、欠血比较、平局）

### 4.2 BattleManager（`engine/battle_manager.py`）

对战生命周期管理器。内部维护 `Dict[str, BattleSession]` 内存存储。

- `init_battle()` — 创建 BattleSession，计算双方可用牌
- `confirm_deck()` — 校验8张牌，锁定牌库，初始化 BattleState
- `submit_card()` — 接收单方提交，双方就绪则调用 `_resolve_round()`
- `get_status()` — 返回对战状态快照
- `get_history()` — 返回完整回合记录

每次操作后异步触发 `base_sync` 将状态写回飞书 Base。

### 4.3 Routes（`routes/`）

**Player Panel 路由**（`routes/player_client.py` — 新增模块）：

| Endpoint | Method | 功能 | 调用方 |
|---|---|---|---|
| `/player` | GET | 玩家面板HTML页面 | 玩家浏览器 |
| `/api/player/lookup` | GET | 查找玩家信息 | 玩家面板JS |
| `/api/player/{name}/battles` | GET | 玩家所有对战列表（活跃+已完成） | 玩家面板JS |
| `/api/player/{name}/battle` | GET | 玩家视角战斗状态（支持 `?battle_id=`） | 玩家面板JS |
| `/api/player/{name}/available-cards` | GET | 玩家可用卡牌列表（支持 `?battle_id=`） | 玩家面板JS |
| `/api/player/select-deck` | POST | 玩家确认8张牌选择 | 玩家面板JS |
| `/api/player/submit-card` | POST | 玩家提交本回合出牌 | 玩家面板JS |
| `/api/player/{name}/battle-logs` | GET | 玩家视角战斗日志（支持 `?battle_id=`） | 玩家面板JS |

**Judge Panel 路由**（`routes/judge_panel.py`）：

| `/judge` | GET | 法官操作面板HTML页面 | 法官浏览器 |
| `/api/judge/pending` | GET | 读取Base待发起记录 | 法官面板JS |

**Battle 路由**（`routes/battle.py` — 对战核心 API）：

| Endpoint | Method | 功能 | 调用方 |
|---|---|---|---|
| `/` | GET | 健康检查，返回服务名+卡牌数 | 任何 |
| `/health` | GET | 健康检查 | Render健康检查 |
| `/api/battle/init` | POST | 初始化对战（需传性相等级） | 手动/程序调用 |
| `/api/battle/init-from-base` | POST | 从Base读玩家数据→初始化对战→写回Base | 法官面板 |
| `/api/battle/confirm-from-base` | POST | 从Base读牌位→确认牌库→开始对战 | Workflow |
| `/api/battle/confirm-deck` | POST | 直接确认牌库 | 手动调用 |
| `/api/battle/webhook` | POST | 接收Base自动化触发的选牌提交 | Workflow |
| `/api/battle/{battle_id}/status` | GET | 查询对战状态 | 调试/Base |
| `/api/battle/{battle_id}/history` | GET | 获取完整战斗记录 | 调试 |

### 4.4 Player Panel 模块扩展原则

Player Panel 是所有玩家功能的**统一入口**。新增玩家系统模块时须遵循：

1. **独立 `section-*`**：每个新模块（背包、成就、属性等）在 `player_client.html` 中拥有独立的 `section-<module-name>` HTML 区域，通过显示/隐藏切换
2. **独立 API 路由前缀**：新模块 API 使用 `/api/player/<module>/*` 格式，避免污染 `/api/player/{name}/battle` 等现有路由
3. **独立 service 函数文件**：`services/` 目录下新增模块对应的 service 文件（如 `services/inventory_service.py`），不与 `player_service.py` 混合
4. **共享状态最小化**：`playerName` 是唯一全局标识符，各模块通过 `playerName` 查找自己的数据，不共享其他模块状态
5. **Base 表隔离**：新模块如需 Base 表格，在 `base_sync.py` 或新模块中定义独立的 `TABLE_*` 常量
6. **不扩展 Battle Dashboard**：战斗相关 UI 和 API 不再增加非战斗字段

### 4.5 Integration（`integration/`）

#### 4.4.1 `feishu_client.py` — 飞书客户端
- 封装飞书 OpenAPI（tenant_access_token 认证）
- `list_records()` — 读取Base表全量记录（自动翻页）
- `add_record()` — 新增记录
- `update_record()` — 更新记录
- 全局单例 `feishu_client`

#### 4.4.2 `base_sync.py` — Base同步
- 将战斗状态写入飞书 Base。当前代码引用的核心表（可扩展）：

  | 表ID | 名称 | 用途 | 引用位置 |
  |---|---|---|---|
  | `tblWciOhRlFFEaSr` | 对战管理 | 对战ID、状态、双方名称、性相、当前回合 | `base_sync.py` |
  | `tblTNAkesS7WlJoR` | 玩家战斗状态 | HP、六资源、看破、牌位1-8、已提交标记 | `base_sync.py`, `battle.py` |
  | `tblyUL90LNC1Snb5` | 对战记录 | 每回合RPS描述、伤害、HP变化、特殊事件 | `base_sync.py` |
  | `tblcmGlzO76H3RQt` | 回合提交 | 提交时间、玩家侧、选择卡牌ID | `base_sync.py` |
  | `tbl0DDzK6ckrqQah` | 玩家可用牌 | 初始化时写入双方可用卡牌列表 | `base_sync.py` |
  | `tblbheflCQ2wTgml` | 法官面板 | 待发起对战记录（法官写入）、对战ID回写 | `judge_panel.py`, `battle.py` |
  | `tbl1NnOpplq3x7Rg` | 玩家表 | 玩家名称→六性相等级映射 | `battle.py` |

  新增表时在对应模块中定义表ID常量，遵循现有命名约定 `TABLE_xxx`。
- 通过环境变量 `FEISHU_APP_ID` 判断是否启用（未配置则跳过同步）
- 全局单例 `base_sync`

---

## 5. API 列表（完整）

| # | Endpoint | Method | 功能 | 调用方 | 请求体 | 返回 |
|---|---|---|---|---|---|---|
| 1 | `/` | GET | 服务信息 | 健康检查 | — | `{"ok": true, "service": "...", "cards": 48}` |
| 2 | `/health` | GET | 健康检查 | Render | — | `{"ok": true, "status": "healthy"}` |
| 3 | `/api/battle/init` | POST | 初始化对战 | 程序调用 | `BattleInitRequest` | `BattleInitResponse` |
| 4 | `/api/battle/init-from-base` | POST | 从Base初始化对战 | 法官面板HTML | `InitFromBaseRequest` | `{"ok": true, "battle_id": "...", ...}` |
| 5 | `/api/battle/confirm-from-base` | POST | 从Base确认牌库 | Workflow | `ConfirmFromBaseRequest` | `{"ok": true, "status": "waiting"/"confirmed"}` |
| 6 | `/api/battle/confirm-deck` | POST | 直接确认牌库 | 程序调用 | `DeckConfirmRequest` | `DeckConfirmResponse` |
| 7 | `/api/battle/webhook` | POST | 接收选牌提交 | Workflow | `WebhookPayload` | `WebhookResponse` |
| 8 | `/api/battle/{battle_id}/status` | GET | 查询对战状态 | 调试 | — | `BattleStatusResponse` |
| 9 | `/api/battle/{battle_id}/history` | GET | 获取战斗记录 | 调试 | — | `BattleHistoryResponse` |
| 10 | `/judge` | GET | 法官面板页面 | 法官浏览器 | — | HTML |
| 11 | `/api/judge/pending` | GET | 获取待发起记录 | 法官面板JS | — | `{"ok": true, "records": [...]}` |

---

## 6. 数据模型

### 6.1 核心数据结构

#### `Card` (card_library.py)
```
id: str              # C01-C06, B01-B07, M01-M07, F01-F07, W01-W07, H01-H07, L01-L07
name: str            # 卡名
category: str        # 进攻/防御/佯攻/打断/状态
aspect: str          # 刃/蛾/铸/冬/心/灯/通用
level_requirement: int  # 0/2/6/10/15
base_damage: int     # 基础伤害
defense_value: int   # 防御减免值
resource_gen: dict   # {"锋芒": 1, "幻影": 1}
resource_consume: dict  # {"蓄力": "all", "洞悉": 1}
# + 20+ 特殊效果标记字段
```

#### `BattleState` (resource_engine.py)
```
hp: int              # 战HP (0-20)
edge: int            # 锋芒 0-3
phantom: int         # 幻影 0-3
charge: int          # 蓄力 0-3
self_chill: int      # 自身寒意 0-3
pulse: int           # 脉动 0-4
read: int            # 洞悉 0-2
insight: int         # 看破 0-2
# + 特殊状态 (iron_armor, invulnerable, next_attack_bonus...)
# + 6性相等级 (blade_level, moth_level...)
```

#### `BattleSession` (battle_manager.py)
```
id: str              # 8位随机ID
player_a_name / player_b_name
player_a_aspects / player_b_aspects  # {"刃": 10, "灯": 4}
player_a_deck / player_b_deck        # 8张卡牌ID
state_a / state_b                    # BattleState
current_round: int
state: str          # initialized/deck_selection/in_progress/finished
submission_a / submission_b  # 当前回合提交
rounds: List[RoundResult]
resolver: RPSResolver
```

#### `RoundResult` (rps_resolver.py)
```
round_number: int
card_a / card_b: Card
rps_type: str       # mutual_damage / a_reduced_b_insight / ...
damage_to_a / damage_to_b: int
special_events: List[str]
battle_ended: bool
winner: str         # "a" / "b" / "draw"
```

### 6.2 Pydantic 请求/响应模型

见 `models/requests.py` 和 `models/responses.py`（共 16 个模型类）。

---

## 7. 部署方式

### 平台
**Render.com** — Web Service (`secret-edinburgh-judge`)

### 启动配置 (`render.yaml`)
```yaml
services:
  - type: web
    name: secret-edinburgh-judge
    env: python
    buildCommand: pip install -r src/judge/requirements.txt
    startCommand: cd src/judge && uvicorn app:app --host 0.0.0.0 --port $PORT
```

### 环境变量

| 变量 | 用途 | 必需 |
|---|---|---|
| `PORT` | 监听端口（Render自动注入） | 是 |
| `FEISHU_APP_ID` | 飞书应用App ID | 是（Base同步需要） |
| `FEISHU_APP_SECRET` | 飞书应用App Secret | 是（Base同步需要） |
| `FEISHU_BASE_TOKEN` | 飞书Base token | 否（默认值已硬编码） |

### Python 依赖 (`requirements.txt`)
```
fastapi>=0.104.0
uvicorn>=0.24.0
httpx>=0.25.0
pydantic>=2.5.0
```

### 启动方式
```bash
# 本地开发
cd src/judge && uvicorn app:app --host 0.0.0.0 --port 8080

# 直接运行
cd src/judge && python app.py
```

### 关键约束
- **无数据库**：所有对战状态存储在内存（`Dict[str, BattleSession]`），服务重启后丢失
- **无认证**：所有API端点无鉴权，依赖 Render 内部网络隔离
- **异步Base同步**：Base写操作使用 `asyncio.create_task()` 非阻塞执行，失败不影响对战流程
