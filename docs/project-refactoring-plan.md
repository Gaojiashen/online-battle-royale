# 密教模拟器S2 项目重构计划

> 分析日期：2026-07-09 | 当前版本：V6战斗系统 + Base集成阶段

---

## 0. 关键发现（探索阶段发现的问题）

### 0.1 设计文档与代码冲突

| 冲突 | 严重度 |
|------|--------|
| **Combat_Constitution.md 第1条**：「禁止预先编排完整行动序列后一次性结算」→ 实际V5/V6采用「双方盲编5步序列同时揭示结算」，完全相反 | 🔴 严重 |
| **combat-system.md（memory）**：称V5为当前版本 → 实际代码已是V6（独占资源词条：锋芒/幻影/蓄力/寒意/脉动/洞悉） | 🟡 中等 |
| **docs/combat/README.md**：称V2为"当前版本" | 🟡 中等 |

### 0.2 Memory文件大量过时

| Memory | 问题 |
|--------|------|
| `npc-design.md` | 引用 `docs/NPC/角色/*.md`（27+个文件已删除） |
| `project-structure.md` | 引用 ~15个已删除的文件路径 |
| `isonbel-storyline.md` | 引用已删除的伊索贝尔28天剧情线文件 |
| `player-panel.md` | 引用已删除的NPC种子数据 |
| `combat-system.md` | 称V5为当前版本 |

### 0.3 重复Memory目录

存在**两套**memory文件：
- `C:\Users\Gao\.claude\projects\D--vibecoding-onling-battle-royale\memory\`（12个，活跃维护中）
- `D:\vibecoding\onling-battle-royale\.claude\projects\D--vibecoding-onling-battle-royale\memory\`（6个，早期快照，已废弃）

### 0.4 未暂存的删除

`git status` 显示约47个文件已从磁盘删除但**未 `git rm`**（docs/NPC/角色/、docs/NPC/剧情/、docs/NPC/规范/、docs/设计笔记/、docs/核心设计原则.md 等），导致仓库处于半清理状态。

### 0.5 版本号冲突

| 主题 | 文档A | 文档B |
|------|-------|-------|
| 蛾飞升等级 | `Current_Narrative_Foundation.md`: Lv14 | `ascension-rules.md`: Lv15 |
| 区域编号 | `地图_区域与连接.md`: ①-㉗（28区） | `item-search-tables.md`: 含㉘"城外庄园" |

---

## 1. 当前模块划分

### 1.1 顶层概览

```
onling-battle-royale/
├── battle-judge/           # 战斗裁判引擎（主力模块）
│   ├── main.py             # FastAPI入口，全部端点
│   ├── models.py           # Pydantic请求/响应模型
│   ├── card_library.py     # 48张V6卡牌定义（dataclass）
│   ├── rps_resolver.py     # RPS核心结算引擎（674行）
│   ├── resource_engine.py  # 六性相资源系统（锋芒/幻影/蓄力/寒意/脉动/洞悉）
│   ├── deck_validator.py   # 多性相可用牌计算 + 8张牌库校验
│   ├── battle_manager.py   # 对战生命周期管理（内存中）
│   ├── webhook_handler.py  # Base webhook路由
│   ├── feishu_client.py    # 飞书BitTable API客户端
│   ├── base_sync.py        # Base数据同步（NEW：未完成）
│   ├── requirements.txt    # fastapi, uvicorn, httpx, pydantic
│   ├── tests/
│   │   └── test_battle_scenarios.py  # 8个测试场景
│   └── battle-judge-spark/ # 飞书妙搭部署变体（子模块）
│       ├── main.py         # ⚠️ 落后于主版本
│       ├── battle_manager.py # ⚠️ 落后于主版本
│       └── ... (其余9个文件与主版本完全一致)
├── tools/
│   └── npc_tracker/        # NPC追踪器Web应用（已废弃）
│       ├── main.py         # FastAPI + 玩家面板 + NPC剧情
│       ├── database.py     # SQLite schema + 查询函数
│       ├── templates/      # Jinja2 HTML模板（7个）
│       └── data/
│           └── npc_tracker.db
├── docs/
│   ├── combat/             # 战斗系统设计文档 + 卡牌Excel + 生成脚本
│   ├── NPC/                # ⚠️ 巨量废弃文件（约60个角色MD + 剧情线）
│   ├── Background/         # 世界观背景文档
│   └── 设计笔记/            # 早期设计笔记（jupyter + markdown）
├── data/                   # 旧数据文件（NPC数据库xlsx等）
├── .claude/
│   ├── settings.local.json # 项目本地权限配置
│   ├── skills/             # 项目宪法（Combat/NPC/Project）
│   └── projects/           # 旧memory镜像
├── render.yaml             # Render部署配置
├── docs.zip                # ⚠️ 垃圾文件
├── auth_qrcode.png         # ⚠️ 垃圾文件
├── structure.txt           # ⚠️ 垃圾文件
├── wf_*.json               # ⚠️ workflow调试临时文件（5个）
├── feishu_install_guidance.md  # ⚠️ 过期安装文档
└── .gitignore
```

### 1.2 系统架构图

```
                    ┌─────────────────────────────┐
                    │     Render.com 部署           │
                    │                              │
   Judge浏览器 ───→ │  /judge (HTML法官面板)        │
                    │  /api/battle/init-from-base  │
                    │  /api/battle/confirm-from-base│
                    │  /api/battle/webhook         │
                    │  /api/battle/{id}/status     │
                    │  /api/battle/{id}/history    │
                    │                              │
                    │  BattleManager (内存)         │
                    │  ├── RPSResolver             │
                    │  ├── ResourceEngine          │
                    │  └── DeckValidator           │
                    │                              │
                    │  FeishuClient ←→ 飞书Base    │
                    │  BaseSync (写入)             │
                    └─────────────────────────────┘

  飞书Base（CB6XbtkLaafJnYsDL8RcHFpEnDg）
  ├── 对战管理        ← API写入
  ├── 玩家战斗状态     ← API写入
  ├── 玩家可用牌       ← API写入
  ├── 对战记录         ← API写入
  ├── 回合提交         → webhook → API
  ├── 卡牌库（48张）   ← 静态参考
  ├── 玩家             ← 手动维护
  └── 法官面板         ← 手动操作

  已废弃：
  tools/npc_tracker/  → FastAPI + SQLite 本地Web应用
```

---

## 2. 文件职责分析

### 2.1 主力模块（battle-judge/）

| 文件 | 行数 | 职责 | 评级 | 问题 |
|------|------|------|------|------|
| `main.py` | ~500 | API入口 + HTML页面 | ⚠️ | 业务逻辑+HTML+路由混在一起 |
| `models.py` | ~140 | 数据模型 | ✅ | 清晰 |
| `card_library.py` | ~520 | 48张卡牌定义 | ✅ | 数据即代码，量大但结构清晰 |
| `rps_resolver.py` | ~670 | RPS结算引擎 | ✅ | 核心逻辑，注释详细 |
| `resource_engine.py` | ~340 | 六性相资源管理 | ✅ | 独立模块，职责单一 |
| `deck_validator.py` | ~280 | 可用牌计算+牌库校验 | ✅ | 独立模块 |
| `battle_manager.py` | ~350 | 对战生命周期 | ⚠️ | 内存存储（重启丢失）+ fire-and-forget同步 |
| `webhook_handler.py` | ~55 | webhook路由 | ✅ | 薄层，合理 |
| `feishu_client.py` | ~120 | 飞书API客户端 | ✅ | 纯API封装 |
| `base_sync.py` | ~250 | Base同步 | ⚠️ | 函数签名与Base表结构紧耦合 |
| `requirements.txt` | 4行 | 依赖声明 | ⚠️ | 极简，缺少版本锁定 |
| `tests/test_battle_scenarios.py` | ~380 | 8个测试 | ✅ | 覆盖核心RPS+资源+校验 |

### 2.2 废弃/半废弃模块

| 文件 | 状态 | 说明 |
|------|------|------|
| `tools/npc_tracker/*` | **废弃** | 已决定改用飞书Base替代Web面板 |
| `data/*` | **废弃** | 早期NPC数据Excel，已被Base替代 |
| `docs/NPC/角色/*` | **废弃** | ~50个NPC角色MD文件，内容在Base中 |
| `docs/NPC/剧情/*` | **废弃** | 剧情线MD+PDF，已迁移或废弃 |
| `docs/NPC/规范/*` | **废弃** | 编写规范，已过时 |
| `docs/设计笔记/*` | **过期** | 早期设计讨论，可归档 |
| `battle-judge/battle-judge-spark/` | **半废弃** | 与主版本有差异，且当前统一用Render |

### 2.3 根目录垃圾文件

| 文件 | 原因 |
|------|------|
| `wf_fix.json, wf_fix2.json, wf_judge_v2.json, wf_judge_v3.json` | Workflow调试临时JSON |
| `docs.zip` | 压缩包（已被解压为docs/） |
| `auth_qrcode.png` | 临时飞书登录二维码 |
| `structure.txt` | 目录结构dump |
| `feishu_install_guidance.md` | 内容过期，且不在docs下 |

---

## 3. 重复和废弃内容

### 3.1 代码重复

| 重复项 | 详情 |
|--------|------|
| **battle-judge-spark/** | 11个文件中9个与主版本完全一致。仅`main.py`和`battle_manager.py`有差异（spark缺少/judge页面和init-from-base端点）。**建议删除整个spark目录**，当前只用Render部署。 |
| **generate_cards.py vs generate_cards_v6.py** | 两个卡牌Excel生成脚本，V5和V6各一个。V5已过时。 |
| **战斗系统_V4 vs V5** | 两个设计文档在docs/combat/中，已被V6代码取代。 |

### 3.2 文档废弃

| 目录 | 文件数 | 状态 |
|------|--------|------|
| `docs/NPC/角色/` | ~50个.md | 全废弃，NPC数据已迁移到其他系统 |
| `docs/NPC/剧情/` | 8个.md/png | 全废弃 |
| `docs/NPC/规范/` | 2个.md | 全废弃 |
| `docs/设计笔记/` | 4个文件 | 过期设计讨论 |
| `docs/NPC/背景NPC汇总.md` | 1个 | 汇总文件，废弃 |

**合计：约65个废弃文件，占docs/的90%以上。**

### 3.3 代码内重复

- `battle_manager.py` 中多处 `import asyncio` + `asyncio.create_task()` 模式重复
- `base_sync.py` 中 `_set_submitted_flag` 和 `_update_player_state` 有相同的list_records查找模式

---

## 4. 不合理目录

| 问题 | 影响 |
|------|------|
| **根目录=垃圾桶** | 5个workflow JSON、auth_qrcode.png、docs.zip、structure.txt、feishu_install_guidance.md 全部散落在根目录 |
| **tools/已空洞化** | 唯一的npc_tracker已被废弃，tools/面临空目录 |
| **data/过时** | Excel和Python脚本是早期原型产物 |
| **docs/NPC/僵尸目录** | ~65个废弃文件，doc结构被它们淹没 |
| **battle-judge-spark/作为子模块** | Git submodule增加复杂度，且内容几乎重复 |
| **.claude/projects/旧memory镜像** | 与C:\Users\Gao\.claude\projects\下的memory重复 |

---

## 5. 推荐目标架构

```
onling-battle-royale/
│
├── .claude/                    # Claude Code配置
│   ├── settings.local.json
│   └── skills/                 # 项目宪法
│
├── src/                        # 源代码（统一入口）
│   └── judge/                  # 战斗裁判引擎（原battle-judge/）
│       ├── __init__.py
│       ├── app.py              # FastAPI应用工厂 + 路由注册
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── battle.py       # 对战API端点
│       │   ├── judge_panel.py  # /judge HTML页面 + pending API
│       │   └── webhook.py      # webhook接收端点
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── card_library.py # 卡牌数据（dataclass → JSON/YAML更适合）
│       │   ├── rps_resolver.py
│       │   ├── resource_engine.py
│       │   ├── deck_validator.py
│       │   └── battle_manager.py
│       ├── integration/
│       │   ├── __init__.py
│       │   ├── feishu_client.py
│       │   └── base_sync.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── requests.py     # 请求模型
│       │   └── responses.py    # 响应模型
│       ├── templates/
│       │   └── judge_panel.html  # 法官面板HTML（从main.py剥离）
│       └── tests/
│           └── test_battle.py
│
├── docs/                       # 纯净文档目录
│   ├── design/                 # 设计文档
│   │   ├── combat-v6.md       # 战斗系统V6（当前版本）
│   │   ├── cards-reference.md # 卡牌参考（从card_library自动生成）
│   │   └── world-setting.md   # 世界观设定
│   ├── archive/                # 归档（V4/V5设计、旧NPC文档等）
│   │   ├── combat-v4.md
│   │   ├── combat-v5.md
│   │   └── npc/               # 旧NPC文档归档
│   └── operations/             # 运维文档
│       ├── deploy.md          # 部署指南
│       └── base-schema.md     # Base表结构说明
│
├── scripts/                    # 工具脚本
│   └── generate_cards_excel.py # 卡牌Excel生成（原generate_cards_v6.py）
│
├── .gitignore
├── render.yaml
├── requirements.txt            # 带版本锁定的依赖
└── README.md                   # 项目说明
```

### 5.1 关键架构决策

| 决策 | 理由 |
|------|------|
| **删除battle-judge-spark/** | 与主版本重复，当前仅用Render，需要时再fork |
| **删除tools/npc_tracker/** | 已确认废弃，功能迁移至Base |
| **删除data/** | 早期原型数据，无当前价值 |
| **删除docs/NPC/全部** | 已废弃，归档到docs/archive/npc/ |
| **main.py拆分为routes/** | 当前500行混杂路由+HTML+业务逻辑 |
| **HTML模板外置** | /judge页面的HTML写在main.py字符串里 |
| **models拆分** | 请求和响应模型分开，更好维护 |
| **requirements.txt升级** | 当前只有4个包名，无版本号 |
| **清理根目录** | 移除5个wf_*.json、docs.zip、auth_qrcode.png等 |

### 5.2 不改变的部分

- **card_library.py**：数据即代码的模式在当前规模下可接受，不需要迁移到JSON/YAML
- **rps_resolver.py + resource_engine.py**：设计良好，只改import路径
- **render.yaml**：保持现有Render部署配置
- **.claude/**：保持Claude Code配置不变

---

## 6. 安全迁移步骤

### Phase 1：清理（零风险，先做）

#### 1.A — 先修部署配置（在删任何文件之前）

| 步骤 | 操作 | 原因 |
|------|------|------|
| **1.A1** | 更新 `render.yaml`：删除 `secret-edinburgh-npc` 服务定义（整个 block），只保留 `secret-edinburgh-judge` | `tools/` 和 `battle-judge-spark/` 即将删除，npc服务的 buildCommand 引用了这两个目录。不先修 render.yaml，删文件后 Render 部署失败 |
| **1.A2** | 在 Render 控制台手动删除 `secret-edinburgh-npc` 服务（如果存在） | 防止 Render 尝试用旧配置重建 |

#### 1.B — 根目录垃圾

| 步骤 | 操作 | 验证 |
|------|------|------|
| **1.B1** | `rm wf_fix.json wf_fix2.json wf_judge_v2.json wf_judge_v3.json docs.zip auth_qrcode.png structure.txt` | `ls *.json` 无 workflow 残留 |
| **1.B2** | `mv feishu_install_guidance.md docs/operations/deploy.md` | 文档归位；`docs/operations/` 不存在则先 `mkdir -p` |
| **1.B3** | 确认 `.gitignore` 覆盖 `__pycache__/` `*.pyc` `*.xlsx` `.venv/` | 防止垃圾重新进入仓库 |

#### 1.C — 暂存已删除文件

| 步骤 | 操作 | 验证 |
|------|------|------|
| **1.C1** | `git rm` 已从磁盘删除的约47个文件（清单见附录A） | `git status` 确认 `deleted:` 条目归零 |

#### 1.D — 废弃模块

| 步骤 | 操作 | 验证 |
|------|------|------|
| **1.D1** | `git rm -r tools/` | NPC Tracker 已确认废弃，功能迁移至 Base |
| **1.D2** | `git rm -r data/` | 早期原型 Excel，无当前价值 |
| **1.D3** | `git rm -r battle-judge/battle-judge-spark/` | 与主版本重复（11文件9个完全一致）；需要时可从 git 历史恢复 |
| **1.D4** | `rm -rf .claude/projects/` | 重复 memory（与 `C:\Users\Gao\.claude\projects\` 下的活跃 memory 重叠）；不属 git 管理，直接删除 |

#### 1.E — 文档归类

| 步骤 | 操作 | 原因 |
|------|------|------|
| **1.E1** | `mkdir -p docs/archive/npc docs/archive/combat-v2 docs/design docs/operations` | 准备目标目录 |
| **1.E2** | 归档 V4/V5 设计文档：`mv docs/combat/战斗系统_V4_设计文档.md docs/combat/战斗系统_V5_设计文档.md docs/archive/` | 只留 V6 在 combat/ |
| **1.E3** | 归档 V2 参考文件到 `docs/archive/combat-v2/`：`mv docs/combat/牌组/行动卡_v2.md docs/combat/牌组/性相卡.md docs/combat/牌组/环境卡.md docs/combat/牌组/规则速查_v2.md docs/combat/牌组/示例对战_v2.md docs/combat/牌组/战斗记录表.md docs/archive/combat-v2/` | **归档，不删除。** 这些 V2 文件不再有参考价值（V6 完全重做），但保留作为设计演变记录。若日后确认不需要，再从 archive 删除 |
| **1.E4** | 删除过时卡牌 Excel：`git rm docs/combat/牌组/战斗牌组_v3.xlsx docs/combat/牌组/战斗牌组_v4.xlsx docs/combat/牌组/战斗牌组_v5.xlsx "docs/combat/牌组/战斗牌组_v5 - 副本.xlsx"` | 存留在 git 历史中可恢复 |
| **1.E5** | 删除 V5 生成脚本：`git rm docs/combat/generate_cards.py` | V5 已被 V6 取代 |
| **1.E6** | 迁移道具系统文件到 `scripts/`：`mkdir -p scripts && mv docs/combat/generate_items_excel.py scripts/ && mv docs/combat/牌组/道具与搜索池.xlsx scripts/` | **保留，归属 scripts/。** 道具搜索系统仍在 memory `item-search-tables.md` 中引用，属于活跃游戏系统而非废弃文档 |

#### 1.F — 活跃文档归位

这些文件是**当前有效**文档，从散落位置移到目标目录：

| 步骤 | 源路径 | 目标路径 |
|------|--------|----------|
| **1.F1** | `docs/世界观_隐秘爱丁堡.md` | `docs/design/world-setting.md` |
| **1.F2** | `docs/地图_区域与连接.md` | `docs/design/map-regions.md` |
| **1.F3** | `docs/爱丁堡地图.svg` | `docs/design/map-edinburgh.svg` |
| **1.F4** | `docs/Background/Current_Narrative_Foundation.md` | `docs/design/main-narrative.md` |
| **1.F5** | `docs/NPC/塞巴斯蒂安·克罗夫特.md` | `docs/design/npc-sebastian-croft.md` |
| **1.F6** | 清理空目录：`rmdir docs/Background docs/NPC 2>/dev/null` | — |

#### 1.G — 更新文档引用（不改代码）

| 步骤 | 操作 |
|------|------|
| **1.G1** | 更新 `docs/combat/README.md`：V2→V6，更新卡牌数量(48张)、资源系统描述（六性相独占资源） |
| **1.G2** | 更新 `.claude/skills/Combat_Constitution.md` 第1条：将「禁止预先编排完整行动序列后一次性结算」改为「双方盲编5步序列，逐步揭示，同时结算（RPS）」以匹配 V6 实际规则 |
| **1.G3** | 解决蛾飞升等级冲突：在 `ascension-rules.md` 和 `Current_Narrative_Foundation.md` 中统一为 **Lv15**（`ascension-rules.md` 是 authority） |

#### 1.H — 更新 Memory 文件

每个 memory 的**具体修改内容**：

| Memory | 问题 | 修改 |
|--------|------|------|
| `npc-design.md` | 引用 `docs/NPC/角色/*.md`（已删除）；称"57个NPC" | (1) 删除 NPC 文件路径引用行；(2) 删除"已完成NPC清单（6个）"段落；(3) 改为标注"NPC 数据已迁移至飞书 Base" |
| `project-structure.md` | 引用约15个已删除路径 | 整篇重写为当前结构（battle-judge/ + docs/ + scripts/）。原始内容保留一段摘要说明"2026-06-28 版本已归档" |
| `combat-system.md` | 称 V5 为当前版本（实际是 V6） | (1) 标题 V5→V6；(2) 卡牌数量 47→48；(3) 资源词条从旧名更新为锋芒/幻影/蓄力/寒意/脉动/洞悉；(4) 新增 V6 核心变更摘要 |
| `isonbel-storyline.md` | 引用已删除的剧情线文件 | 删除文件路径引用，改为标注"剧情线内容已迁移至飞书 Base；原始 MD 文件已归档" |
| `player-panel.md` | 引用已删除的 NPC 种子数据路径 | 标注"NPC Tracker 已于 2026-07-09 废弃，玩家面板功能迁移至飞书 Base" |

### Phase 2：重构（需验证）

#### 2.A — 先更新 Render 配置（在移动任何文件之前）

| 步骤 | 操作 |
|------|------|
| **2.A1** | 更新 `render.yaml` 中 `secret-edinburgh-judge` 的 `buildCommand`：`pip install -r src/judge/requirements.txt` |
| **2.A2** | 更新 `startCommand`：`cd src/judge && uvicorn app:app --host 0.0.0.0 --port $PORT` |
| **2.A3** | 确认 `render.yaml` 只剩一个服务定义（npc 服务已在 Phase 1 删除） |

#### 2.B — 创建目录结构

| 步骤 | 操作 | 验证 |
|------|------|------|
| **2.B1** | 创建 `src/judge/` 及其子目录：`mkdir -p src/judge/routes src/judge/engine src/judge/integration src/judge/models src/judge/templates` | 空壳就位 |
| **2.B2** | 在各级写入空 `__init__.py` | import 不会因缺失 `__init__.py` 失败 |

#### 2.C — 拆分并移动文件

##### 2.C1：engine 组（纯战斗逻辑，不依赖 FastAPI/feishu）

| 源路径 | 目标路径 |
|--------|----------|
| `battle-judge/card_library.py` | `src/judge/engine/card_library.py` |
| `battle-judge/resource_engine.py` | `src/judge/engine/resource_engine.py` |
| `battle-judge/rps_resolver.py` | `src/judge/engine/rps_resolver.py` |
| `battle-judge/deck_validator.py` | `src/judge/engine/deck_validator.py` |
| `battle-judge/battle_manager.py` | `src/judge/engine/battle_manager.py` |

##### 2.C2：integration 组（外部系统集成）

| 源路径 | 目标路径 |
|--------|----------|
| `battle-judge/feishu_client.py` | `src/judge/integration/feishu_client.py` |
| `battle-judge/base_sync.py` | `src/judge/integration/base_sync.py` |
| `battle-judge/webhook_handler.py` | `src/judge/integration/webhook_handler.py` |

##### 2.C3：models 拆分

| 源 | 目标 | 内容 |
|----|------|------|
| `battle-judge/models.py` | `src/judge/models/requests.py` | `BattleInitRequest`, `DeckConfirmRequest`, `InitFromBaseRequest`, `ConfirmFromBaseRequest`, `WebhookPayload` |
| | `src/judge/models/responses.py` | `CardInfo`, `BattleInitResponse`, `DeckConfirmResponse`, `RoundLog`, `WebhookResponse`, `PlayerStateInfo`, `BattleStatusResponse`, `BattleHistoryResponse` |

##### 2.C4：main.py 拆分

| 目标文件 | 内容 |
|----------|------|
| `src/judge/app.py` | FastAPI 应用工厂（`create_app()`）、CORS 中间件、lifespan、路由注册 |
| `src/judge/routes/battle.py` | `/api/battle/init`, `/api/battle/init-from-base`, `/api/battle/confirm-deck`, `/api/battle/confirm-from-base`, `/api/battle/webhook`, `/api/battle/{id}/status`, `/api/battle/{id}/history` |
| `src/judge/routes/judge_panel.py` | `/judge`（HTML 页面）, `/api/judge/pending` |
| `src/judge/templates/judge_panel.html` | 从 `main.py` 字符串中提取的完整 HTML（CSS + JS inline） |

##### 2.C5：测试 + 依赖迁移

| 源 | 目标 |
|----|------|
| `battle-judge/tests/test_battle_scenarios.py` | `src/judge/tests/test_battle_scenarios.py` |
| `battle-judge/requirements.txt` | `src/judge/requirements.txt` |

#### 2.D — 更新 import 路径

所有内部 import 改为新路径。关键变更：

| 旧 import | 新 import |
|-----------|-----------|
| `from card_library import ...` | `from engine.card_library import ...` |
| `from resource_engine import ...` | `from engine.resource_engine import ...` |
| `from rps_resolver import ...` | `from engine.rps_resolver import ...` |
| `from deck_validator import ...` | `from engine.deck_validator import ...` |
| `from battle_manager import ...` | `from engine.battle_manager import ...` |
| `from models import ...` | `from models.requests import ...` / `from models.responses import ...` |
| `from feishu_client import ...` | `from integration.feishu_client import ...` |
| `from base_sync import ...` | `from integration.base_sync import ...` |
| `from webhook_handler import ...` | `from integration.webhook_handler import ...` |

> **注意**：所有文件移到 `src/judge/` 子包后，同级 import 无需 `src.judge.` 前缀。`card_library.py` 的 `if __name__ == "__main__": print_stats()` 需更新或移除。

#### 2.E — 验证

| 步骤 | 操作 | 验证标准 |
|------|------|----------|
| **2.E1** | `cd src/judge && python -c "from engine.card_library import ALL_CARDS; print(len(ALL_CARDS))"` | 输出 `48` |
| **2.E2** | `cd src/judge && python tests/test_battle_scenarios.py` | 8/8 全部通过 |
| **2.E3** | `cd src/judge && uvicorn app:app --port 8080`，访问 `/health` | `{"ok":true,"status":"healthy"}` |
| **2.E4** | `git rm -r battle-judge/` | 旧目录删除；确认无文件引用旧路径 |
| **2.E5** | 提交并 push，观察 Render 部署日志 | 构建成功，服务正常 |

### Phase 3：优化（长期）

| 步骤 | 操作 |
|------|------|
| 3.1 | 用Redis/SQLite替代BattleManager的内存存储 |
| 3.2 | `base_sync.py` 改为事件驱动（publish/subscribe），减少list_records轮询 |
| 3.3 | 卡牌数据从Python dataclass迁移到可热加载的配置格式 |
| 3.4 | 添加CI（GitHub Actions跑测试） |

---

## 7. 风险矩阵

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| render.yaml 引用断裂导致部署失败 | 🔴 高 | **已在 Phase 1.A 和 2.A 中前置处理**——先修配置再删文件 |
| 删除 spark 导致需要时无法恢复 | 🟢 低 | Git 历史可恢复 |
| 删除 tools/npc_tracker 导致数据丢失 | 🟢 低 | SQLite 数据无当前价值；代码在 git 历史中 |
| 拆分 main.py 引入循环 import | 🟡 中 | 现有 import 图已确认无环（card_library 和 models 是唯二根节点）；拆分后 engine 不依赖 routes，不会引入新环 |
| base_sync.py 重构导致 Base 写入失败 | 🟡 中 | Phase 3 才改，先稳定现有实现 |
| Phase 2 import 路径漏改 | 🟡 中 | 步骤 2.D 提供完整对照表；2.E 验证步骤会在部署前暴露问题 |

---

## 8. 一句话总结

> 项目核心清晰（battle-judge/的11个文件），外围垃圾多（~65个废弃文档、根目录7个临时文件、spark重复、npc_tracker废弃模块）。建议先删垃圾（零风险），再拆分main.py（中等风险），最后做架构升级（长期）。

---

## 附录A：Phase 1.C1 待 git rm 的文件完整清单

从 `git status` 提取的 ~47 个已从磁盘删除的文件：

**docs/NPC/剧情/**（8个）
- `剧情线_伊索贝尔的28天.md`
- `剧情线_伊索贝尔的28天.pdf`
- `剧情线_埃德蒙的灯之真相.md`
- `剧情线_海伦娜的铸之容器.md`
- `剧情线_莉莉的叉路口.md`
- `剧情线_西尔维娅的冬之尽头.md`
- `剧情线_邓肯的夜间地图.md`
- `剧情线_马库斯的刃之路.md`

**docs/NPC/角色/**（~27个，包括全部57个NPC中的角色卡文件）

**docs/NPC/规范/**（2个）
- `NPC剧情线编写原则.md`
- `NPC剧情线编写规范.md`

**docs/NPC/**（1个）
- `背景NPC汇总.md`

**docs/设计笔记/**（4个）
- `ProjectVision.ipynb`
- `NPC剧情线作为玩家入口.md`
- `结算不再等所有人.md`
- `新建 文本文档.txt`

**docs/** 根级（3个）
- `核心设计原则.md`
- `行动框架_动词表.md`
- `行动框架_裁定流程.md`
- `大型事件时间线.md`

---

## 附录B：Phase 1 完成后的预期文件结构

```
onling-battle-royale/
├── .claude/
│   ├── settings.local.json
│   └── skills/
│       ├── Combat_Constitution.md       # 已更新：V6实际规则
│       ├── NPC_Design_Constitution.md
│       └── Project_Constitution.md
├── battle-judge/                        # 不动，Phase 2 才迁移
├── docs/
│   ├── design/                          # 活跃设计文档（Phase 1.F 迁移到此）
│   │   ├── world-setting.md
│   │   ├── map-regions.md
│   │   ├── map-edinburgh.svg
│   │   ├── main-narrative.md
│   │   └── npc-sebastian-croft.md
│   ├── combat/
│   │   ├── README.md                    # 已更新：V6
│   │   ├── generate_cards_v6.py
│   │   └── 牌组/
│   │       └── 战斗牌组_v6.xlsx          # 唯一保留的卡牌Excel
│   ├── operations/
│   │   └── deploy.md                    # 原feishu_install_guidance.md
│   └── archive/
│       ├── combat-v4.md
│       ├── combat-v5.md
│       ├── combat-v2/                   # V2参考文件归档
│       └── npc/                         # 旧NPC文档归档（如后续需要）
├── scripts/
│   ├── generate_cards_v6.py             # (保留在docs/combat/或迁到此)
│   ├── generate_items_excel.py
│   └── 道具与搜索池.xlsx
├── .gitignore
├── render.yaml                          # 已更新：只含judge服务
└── requirements.txt
```
