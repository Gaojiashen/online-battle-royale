# CLAUDE.md — 密教模拟器S2 在线沙盒后端开发规则

> 本文档是 Claude 在本项目中的**开发规则**，不是业务介绍。
> 修改代码前必须遵循本文档。

---

## 1. 项目核心原则

### 1.1 项目边界

**当前架构：Player Panel + Battle Engine**

`src/judge/` 是整个游戏的**唯一后端服务**，不再是单纯的"战斗裁判引擎"。

**已实现模块：**
- PvP 战斗裁判引擎（完整生命周期 + RPS 结算 + 资源流转）
- Player Panel（玩家面板 — `/player` HTML 页面，是玩家进入游戏后的主入口）
- Judge Panel（法官面板 — `/judge` HTML 页面，用于发起对战）
- 飞书 Base 双向同步

**Player Panel 是玩家主入口。** Battle Dashboard（选牌、出牌、战斗回顾）是 Player Panel 的**子模块**，通过 `section-battle` 区域承载。战斗不是全部内容。

**未来模块（在 src/judge/ 内扩展）：**
- 背包系统、成就系统、属性面板、探索、飞升仪式等

**代码模块边界：**
新增玩家功能模块时：
- 在 `templates/player_client.html` 中新增独立的 `section-*` 区域
- 在 `routes/` 中新增独立的路由文件（如 `routes/inventory.py`）
- 在 `services/` 中新增独立业务模块（如 `services/inventory_service.py`）
- **不要**在 `section-battle` 内追加非战斗 UI
- **不要**在 `player_service.py`、`routes/player_client.py` 中追加非战斗业务逻辑

### 1.2 部署单元 = `src/judge/`

本项目部署于 Render.com 的只是 `src/judge/` 目录。该目录之外的文件（`docs/`、`scripts/`、`.claude/`）不会部署到生产环境。

### 1.3 Player Panel 模块化约束

**Player Panel 是玩家进入游戏后的主入口，不是单纯的战斗页面。**

新增玩家系统模块（背包、成就、属性等）时：

1. **前端隔离**：在 `player_client.html` 中新建 `section-<module>` HTML 区域，通过 `classList.toggle('hidden')` 切换显示
2. **路由隔离**：新建 `routes/<module>.py`，API 前缀使用 `/api/player/<module>/` 
3. **业务隔离**：新建 `services/<module>_service.py`，不向 `player_service.py` 追加
4. **模型隔离**：新建 `models/<module>_requests.py` 和 `models/<module>_responses.py`
5. **共享状态**：`playerName` 是唯一全局标识符，通过它查找模块数据
6. **禁止**：不得在 `section-battle`、`battle_service`、`battle_routes` 中追加非战斗功能

### 1.4 分层架构

```
routes/        ← 只处理 HTTP：解析请求、调用下层、返回响应
  ↓
engine/        ← 纯逻辑：无HTTP依赖、无飞书依赖、可独立测试
  ↓
integration/   ← 外部服务：飞书API调用、Base同步
models/        ← 数据定义：Pydantic请求/响应模型
```

**各层职责严格分离。禁止跨层调用（如 engine 直接调 feishu_client）。**

### 1.4 战斗引擎是纯逻辑

`engine/` 下的所有模块接受 Python 对象作为输入，返回 Python 对象作为输出。不依赖 FastAPI、HTTP、飞书。不读取环境变量。不发起网络请求。

### 1.5 状态存储在内存

所有对战状态存储在 `BattleManager._battles: Dict[str, BattleSession]`。无数据库、无文件持久化。服务重启后状态全部丢失。

---

## 2. 禁止事项

### 2.0 飞书 Base 是当前阶段的数据管理与交互平台

- 当前阶段，飞书 Base 承担数据管理和轻量交互角色。
- 玩家通过 Base 表格完成：查看可用卡牌、选择8张牌库、逐回合提交出牌、查看战斗状态与历史记录。
- 法官通过 `/judge` Dashboard 页面 + Base「法官面板」表发起对战。
- 飞书 Workflow 是 Base 和本服务之间的桥梁：监听 Base 记录变更 → HTTP POST 到本服务 → 本服务结算后写回 Base。
- **不作为长期玩家客户端架构约束**。未来可以增加独立的 Player Client（Web/App），通过调用本服务 API 替代 Base + Workflow 链路，不违反当前架构。
- **设计原则**：业务逻辑在本服务，自动化在 Workflow，数据/交互在 Base。三者各司其职，不在 Workflow 中写业务逻辑，不在本服务中做UI渲染。

### 2.1 禁止无理由修改目录结构

- `src/judge/` 的子目录布局（`engine/`, `routes/`, `integration/`, `models/`, `templates/`, `tests/`）是经过设计的架构分层。
- **禁止无理由修改**：新增/删除/重命名子目录必须说明原因并与用户讨论确认后方可进行。
- 新增模块优先放入已有目录；若确实需要新目录，先说明理由。
- 不得在 `src/judge/` 外创建与部署相关的代码。

### 2.2 禁止重复实现已有功能

修改前必须先搜索是否有已有实现：
- 卡牌相关 → 查 `card_library.py`
- 战斗结算 → 查 `rps_resolver.py`
- Base读写 → 查 `feishu_client.py`
- Base同步 → 查 `base_sync.py`

### 2.3 禁止删除已有API端点

`routes/battle.py` 中的 7 个端点 + `routes/judge_panel.py` 的 2 个端点 + `app.py` 的 2 个基础端点都不可删除。新增端点可以，但不能改变已有端点的路径或方法。

### 2.4 禁止在 Workflow 中实现业务逻辑

飞书 Workflow 只负责触发 webhook。所有战斗逻辑（选牌校验、RPS结算、资源计算、胜负判定）必须在 `src/judge/` 中实现。

### 2.5 禁止把业务逻辑写进 routes

Routes 方法不超过 15 行（不含 docstring）。核心逻辑必须放在 `engine/` 或 `integration/` 中。

### 2.6 禁止硬编码新配置

飞书 Base Token、表ID 等配置项，**新加的**必须从环境变量读取并提供默认值。不能直接在代码中写死新的外部依赖标识符。（已有硬编码的 Base token 和表ID 暂时保留。）

### 2.7 禁止在 engine 中引入异步

`engine/` 层不使用 `async/await`。它只做同步计算。异步操作（如 Base 同步）由 `battle_manager.py` 或 routes 层通过 `asyncio.create_task()` 触发。

### 2.8 禁止无关重构

- 修改代码时，只修改与当前任务直接相关的部分。
- **禁止**在修复 bug 时顺手重构无关模块。
- **禁止**在添加功能时顺便调整已有代码风格（除非该风格违反本规则）。
- **禁止**大规模重命名或移动文件，除非该重命名是当前任务的明确要求。
- 如果发现代码中有需要改进的地方但与当前任务无关，先记录下来，向用户报告，获得确认后再单独处理。

### 2.9 前端按钮交互规范

**所有触发异步操作的按钮必须提供即时反馈**：

| 时机 | 行为 |
|------|------|
| 点击瞬间 | `setBtnLoading(btn, 'xxx中...')` — disabled + 文字变更 |
| 请求成功 | 进入下一状态，按钮保持 disabled 或隐藏 |
| 请求失败 | `resetBtn(btn)` — 恢复 disabled=false + 原文案 + `showError()` |
| 异常 | `resetBtn(btn)` + `showError('网络异常，请稍后重试')` + `console.error()` |

**禁止：** 用户点击按钮后无任何视觉反馈，在 `await fetch()` 完成前按钮仍可重复点击。

**统一辅助函数**（已在 `player_client.html` 和 `judge_panel.html` 中定义）：
```javascript
function setBtnLoading(btn, text) {
  btn._origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = text;
}
function resetBtn(btn) {
  btn.disabled = false;
  if (btn._origText) btn.textContent = btn._origText;
}
```

---

## 3. 修改代码流程

### 3.1 修改前

1. **分析影响范围**：使用 Grep 搜索被修改函数/类的所有引用
2. **查找已有实现**：确认是否有重复功能可复用
3. **说明计划**：向用户报告
   - 要修改哪些文件
   - 修改原因
   - 影响范围
   - 潜在风险

### 3.2 修改后

1. **汇报修改文件清单**：列出每个被修改的文件及其变更摘要
2. **运行测试**：
   ```bash
   cd src/judge && python -m pytest tests/ -v
   ```
   或直接运行：
   ```bash
   cd src/judge && python tests/test_battle_scenarios.py
   ```
3. **验证卡牌统计**（如果修改了 card_library.py）：
   ```bash
   cd src/judge && python -c "from engine.card_library import print_stats; print_stats()"
   ```
4. **如测试失败，必须在提交前修复**

---

## 4. 架构约束

### 4.1 Engine 保持纯逻辑

- 输入：Python dataclass 对象
- 输出：Python dataclass 对象
- 不依赖 FastAPI / HTTP / 飞书
- 不使用 `async/await`
- 不读取环境变量
- 不发起网络请求

### 4.2 Routes 只处理 HTTP

- 解析请求参数
- 调用 `app.state.battle_manager` 或 `app.state.webhook_handler`
- 返回响应
- 处理异常，转换为 HTTPException

### 4.3 Integration 处理外部服务

- `feishu_client.py`：飞书 OpenAPI 的 HTTP 调用
- `base_sync.py`：将战斗状态转化为 Base 表格字段并写入。当前覆盖 7 张表（见 ARCHITECTURE.md），同步内容包括：对战初始化、牌库确认、回合提交记录、回合结算结果、玩家资源状态更新、对战结束。
- Base 同步是**非阻塞的**：所有 `sync_*` 方法通过 `asyncio.create_task()` 异步执行，同步失败仅记录日志，不影响对战流程。
- 通过 `FEISHU_APP_ID` 环境变量判断是否启用。未配置时所有 `sync_*` 方法静默跳过（`self._enabled = False`）。

### 4.4 Models 只定义数据结构

- 使用 Pydantic BaseModel
- 不包含业务逻辑
- requests.py 和 responses.py 分离

### 4.5 BattleManager 管理生命周期

- 维护内存中的对战状态字典 `_battles: Dict[str, BattleSession]`
- 提供对战全生命周期操作：`init_battle()` → `confirm_deck()` → `submit_card()` → `_resolve_round()`
- 协调 Engine 层（RPSResolver 结算、DeckValidator 校验）和 Integration 层（base_sync 异步写回 Base）
- 自身不包含结算逻辑（委托给 RPSResolver），不包含资源操作（委托给 ResourceEngine）
- Base 同步在此层通过 `asyncio.create_task()` 非阻塞触发，确保结算延迟不受 Base 网络影响

---

## 5. Debug 规范

### 5.1 先定位，再修改

当用户报告问题时：
1. 阅读相关代码
2. 分析可能的根因
3. 向用户报告诊断结果
4. 确认后再修改

**禁止在没有定位根因的情况下直接重构代码。**

### 5.2 测试优先验证

- 修改结算逻辑 → 运行 `rps_resolver.py` 内置测试
- 修改资源系统 → 运行 `resource_engine.py` 内置测试
- 修改组牌 → 运行 `deck_validator.py` 内置测试
- 修改卡牌 → 运行 `test_battle_scenarios.py` 全量

### 5.3 添加日志

生产问题排查依赖日志。关键操作点已有 `logger.info()` 和 `logger.error()`。

新增分支逻辑时，异常路径必须加 `logger.error()`。

---

## 6. 代码风格

### 6.1 匹配现有风格

- 文件头：模块级 docstring 说明模块用途
- 注释：使用中文
- 分隔符：`# ═══════...` 用于分段
- 类型注解：函数签名使用 Python type hints
- Dataclass：优先使用 `@dataclass`（纯数据）或 Pydantic（API模型）

### 6.2 命名约定

- 文件名：snake_case
- 类名：PascalCase
- 函数/变量：snake_case
- 常量：UPPER_SNAKE_CASE

### 6.3 导入约定

- engine 模块导入 engine 模块使用 `from engine.xxx import ...`（因为运行时工作目录是 src/judge/）
- routes 和 integration 也用同样方式导入
- 不要使用相对导入（`from .xxx import ...`）

---

## 7. 关键文件速查

| 文件 | 职责 | 修改时注意 |
|---|---|---|
| `app.py` | FastAPI 入口 | 只改 startup/lifespan，不添加业务逻辑 |
| **Player Panel** | | |
| `templates/player_client.html` | 玩家面板（Player Panel 入口） | 新增模块用独立 `section-*`，不扩展 `section-battle` |
| `routes/player_client.py` | 玩家面板 API（8个端点） | 新模块应新建路由文件，不在此追加 |
| `services/player_service.py` | 玩家视角战斗查询 + 对战历史 | 新模块应新建 service 文件，不在此追加 |
| `models/player_requests.py` | 玩家面板请求模型 | |
| `models/player_responses.py` | 玩家面板响应模型 | |
| **Battle Engine** | | |
| `engine/card_library.py` | 48张卡牌定义 | 修改卡牌数据必须同步更新测试 |
| `engine/rps_resolver.py` | RPS结算核心 | ~600行，修改结算逻辑风险最大 |
| `engine/resource_engine.py` | 6资源流转 | 修改资源规则必须更新内置测试 |
| `engine/deck_validator.py` | 组牌校验 | DECK_SIZE=8 是常数 |
| `engine/battle_manager.py` | 对战生命周期（内存状态机） | `session.battle_id` 是唯一关联键；`currentBattleId` 前端全局变量绑定当前战斗 |
| **Routes** | | |
| `routes/battle.py` | 对战核心API | 7个端点，不可删除 |
| `routes/webhook.py` | Webhook处理 | 薄路由层，委托给 BattleManager |
| `routes/judge_panel.py` | 法官面板 | 硬编码了 Base token 和表ID |
| **Integration** | | |
| `integration/feishu_client.py` | 飞书API | 全局单例，基于环境变量 |
| `integration/base_sync.py` | Base同步 | 7张表，非阻塞异步 |
| **Deploy** | | |
| `render.yaml` | 部署配置 | 不要随意修改 buildCommand/startCommand |

## 8.分层规则

routes:
HTTP入口，只负责请求解析

services:
业务流程编排

engine:
纯游戏逻辑

integration:
外部系统访问