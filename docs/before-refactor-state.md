# 重构前项目状态快照

> 记录时间：2026-07-09 | 即将执行：project-refactoring-plan.md Phase 1-3
> 用途：回滚参考、迁移验证对照

---

## 1. Git 状态

```
Branch: main (tracking origin/main)
Last commit: 8895c47 feat: /judge 法官操作面板 + pending API
Commits total: 7

Modified (not staged):
  - battle-judge/battle_manager.py  (removed async create_task for base_sync)
  - battle-judge/main.py            (sync writes + write_errors reporting)
  - battle-judge/battle-judge-spark (submodule, stale)

Deleted from disk (not staged, ~47 files):
  - docs/NPC/剧情/* (8 files)
  - docs/NPC/角色/* (~27 files)
  - docs/NPC/规范/* (2 files)
  - docs/NPC/背景NPC汇总.md
  - docs/设计笔记/* (4 files)
  - docs/核心设计原则.md
  - docs/行动框架_动词表.md
  - docs/行动框架_裁定流程.md
  - docs/大型事件时间线.md
  - docs/新建 文本文档.txt
```

---

## 2. 完整目录结构

```
onling-battle-royale/
│
├── .claude/
│   ├── settings.local.json                 # Bash/WebFetch/lark-cli 权限
│   ├── scheduled_tasks.json                # 空任务列表
│   ├── scheduled_tasks.lock
│   ├── skills/
│   │   ├── Combat_Constitution.md          # ⚠️ 与V6代码冲突
│   │   ├── NPC_Design_Constitution.md
│   │   └── Project_Constitution.md
│   └── projects/D--vibecoding-onling-battle-royale/memory/   # ⚠️ 过期副本
│       ├── MEMORY.md
│       ├── action-framework-v1.md
│       ├── communication-restriction.md
│       ├── game-concept.md
│       ├── next-steps.md
│       ├── project-vibe.md
│       └── 进度-2026-06-24.md
│
├── battle-judge/                            # 主力模块
│   ├── main.py                              # FastAPI入口 (521行)
│   ├── models.py                            # Pydantic模型 (148行)
│   ├── card_library.py                      # 48张V6卡牌 (525行)
│   ├── rps_resolver.py                      # RPS结算引擎 (674行)
│   ├── resource_engine.py                   # 六性相资源 (343行)
│   ├── deck_validator.py                    # 牌库校验 (281行)
│   ├── battle_manager.py                    # 对战生命周期 (365行)
│   ├── webhook_handler.py                   # webhook路由 (56行)
│   ├── feishu_client.py                     # 飞书API (122行)
│   ├── base_sync.py                         # Base同步 (331行)
│   ├── requirements.txt                     # fastapi uvicorn httpx pydantic
│   ├── auth_qrcode.png                      # ⚠️ 垃圾文件
│   ├── tests/
│   │   └── test_battle_scenarios.py         # 8个测试 (382行)
│   └── battle-judge-spark/                  # ⚠️ 子模块/重复
│       ├── .gitignore
│       ├── README.md
│       ├── requirements.txt
│       ├── main.py                          # 330行 (缺少/judge)
│       ├── models.py                        # 与主版本一致
│       ├── card_library.py                  # 与主版本一致
│       ├── rps_resolver.py                  # 与主版本一致
│       ├── resource_engine.py               # 与主版本一致
│       ├── deck_validator.py                # 与主版本一致
│       ├── battle_manager.py                # +10行 (internal sync)
│       ├── webhook_handler.py               # 与主版本一致
│       ├── feishu_client.py                 # 与主版本一致
│       ├── base_sync.py                     # 与主版本一致
│       └── tests/
│           └── test_battle_scenarios.py     # 与主版本一致
│
├── tools/                                   # NPC Tracker (已废弃)
│   ├── requirements.txt                     # fastapi uvicorn jinja2 aiosqlite
│   └── npc_tracker/
│       ├── .gitignore
│       ├── Procfile
│       ├── render.yaml
│       ├── main.py                          # FastAPI (951行)
│       ├── database.py                      # SQLite (2196行)
│       ├── static/style.css
│       ├── templates/
│       │   ├── base.html
│       │   ├── index.html
│       │   ├── connections.html
│       │   ├── npc_detail.html
│       │   ├── players.html
│       │   ├── player_detail.html
│       │   └── player_panel.html
│       └── data/
│           └── npc_tracker.db
│
├── data/                                    # 早期原型 (废弃)
│   ├── NPC数据库.xlsx
│   ├── 角色卡.xlsx
│   ├── create_character_card.py
│   └── create_npc_db.py
│
├── docs/                                    # 设计文档
│   ├── 世界观_隐秘爱丁堡.md                  # 当前有效
│   ├── 地图_区域与连接.md                    # 当前有效
│   ├── 爱丁堡地图.svg                        # 当前有效
│   ├── project-refactoring-plan.md          # 本文档的配套计划
│   ├── Background/
│   │   └── Current_Narrative_Foundation.md   # 当前有效
│   ├── NPC/
│   │   └── 塞巴斯蒂安·克罗夫特.md            # 新增 (untracked)
│   └── combat/
│       ├── README.md                        # ⚠️ 过时 (V2)
│       ├── 战斗系统_V4_设计文档.md           # 被V6取代
│       ├── 战斗系统_V5_设计文档.md           # 被V6取代
│       ├── generate_cards.py                # V5脚本 (被V6取代)
│       ├── generate_cards_v6.py             # V6脚本 (当前)
│       ├── generate_items_excel.py          # 道具系统 (活跃)
│       └── 牌组/
│           ├── 战斗牌组_v6.xlsx              # V6卡牌 (当前)
│           ├── 战斗牌组_v5.xlsx              # 过时
│           ├── 战斗牌组_v5 - 副本.xlsx       # 重复
│           ├── 战斗牌组_v4.xlsx              # 过时
│           ├── 战斗牌组_v3.xlsx              # 过时
│           ├── 道具与搜索池.xlsx             # 道具系统 (活跃)
│           ├── 行动卡_v2.md                  # V2过时
│           ├── 性相卡.md                     # V2过时
│           ├── 环境卡.md                     # V2过时
│           ├── 规则速查_v2.md                # V2过时
│           ├── 示例对战_v2.md                # V2过时
│           └── 战斗记录表.md                 # V2过时
│
├── render.yaml                              # Render部署 (2个服务)
├── .gitignore
│
├── ⚠️ 根目录垃圾:
├── wf_fix.json, wf_fix2.json               # workflow调试
├── wf_judge_v2.json, wf_judge_v3.json      # workflow调试
├── docs.zip                                 # 压缩包
├── auth_qrcode.png                          # 临时二维码
├── structure.txt                            # 目录dump
└── feishu_install_guidance.md               # 过期安装指南
```

---

## 3. 当前运行方式

### 3.1 开发环境

| 项目 | 值 |
|------|-----|
| Python | 3.10 (conda: `online-battle-royale`) |
| 路径 | `D:\vibecoding\onling-battle-royale` |
| 入口 | `battle-judge/main.py` |
| 启动 | `cd battle-judge && uvicorn main:app --host 0.0.0.0 --port 8080` |

### 3.2 测试入口

| 项目 | 值 |
|------|-----|
| 文件 | `battle-judge/tests/test_battle_scenarios.py` |
| 运行 | `cd battle-judge && python tests/test_battle_scenarios.py` |
| 测试数 | 8个 |
| 框架 | 无（纯 `assert`，`if __name__ == "__main__"` 自执行） |
| 覆盖 | card_library, deck_validator, resource_engine, rps_resolver |

### 3.3 外部依赖

**battle-judge/requirements.txt** (无版本号):
```
fastapi
uvicorn
httpx
pydantic
```

**隐式依赖** (不在 requirements.txt 但代码使用):
- `asyncio` (标准库)
- `uuid` (标准库)
- `logging` (标准库)
- `json` (标准库)
- `os` (标准库)
- `datetime` (标准库)
- `copy` (标准库)

---

## 4. Render 部署配置

### 4.1 render.yaml (根目录)

```yaml
services:
  - type: web
    name: secret-edinburgh-npc          # ← 即将删除
    env: python
    buildCommand: pip install -r tools/requirements.txt && pip install -r battle-judge/battle-judge-spark/requirements.txt
    startCommand: cd tools/npc_tracker && uvicorn main:app --host 0.0.0.0 --port $PORT

  - type: web
    name: secret-edinburgh-judge       # ← 保留
    env: python
    buildCommand: pip install -r battle-judge/requirements.txt
    startCommand: cd battle-judge && uvicorn main:app --host 0.0.0.0 --port $PORT
```

### 4.2 运行时环境变量 (Render 控制台)

| 变量 | 值 | 用途 |
|------|-----|------|
| `FEISHU_APP_ID` | `cli_aac5a0e579785cda` | 飞书应用ID |
| `FEISHU_APP_SECRET` | (已配置) | 飞书应用密钥 |
| `FEISHU_BASE_TOKEN` | (未配置) | 默认 `CB6XbtkLaafJnYsDL8RcHFpEnDg` |

### 4.3 当前端点 (生产)

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/judge` | 法官操作面板 (HTML) |
| GET | `/api/judge/pending` | 待发起对战列表 |
| POST | `/api/battle/init` | 初始化对战 |
| POST | `/api/battle/init-from-base` | 从Base初始化 (含同步写入) |
| POST | `/api/battle/confirm-deck` | 确认牌库 |
| POST | `/api/battle/confirm-from-base` | 从Base确认牌库 |
| POST | `/api/battle/webhook` | Base webhook接收 |
| GET | `/api/battle/{id}/status` | 对战状态 |
| GET | `/api/battle/{id}/history` | 对战历史 |

---

## 5. 主要模块关系

### 5.1 Import 依赖图

```
card_library.py          (独立 — 零内部依赖)
     ↑
models.py               (独立 — 零内部依赖)
     ↑
resource_engine.py       → card_library
     ↑
rps_resolver.py          → card_library, resource_engine
     ↑
deck_validator.py        → card_library
     ↑
feishu_client.py         (独立 — 仅依赖 httpx)
     ↑
base_sync.py             → feishu_client
     ↑
battle_manager.py        → card_library, deck_validator, resource_engine, rps_resolver, models, base_sync
     ↑                ↑
webhook_handler.py       → models, battle_manager
     ↑
main.py                  → 以上全部 + fastapi
```

- **根节点**: `card_library.py`, `models.py`, `feishu_client.py`
- **核心枢纽**: `battle_manager.py` (连接 engine 和 integration)
- **无循环依赖**

### 5.2 文件分组

| 组 | 文件 | 职责 |
|----|------|------|
| **数据** | `card_library.py`, `models.py` | 卡牌定义、API契约 |
| **引擎** | `rps_resolver.py`, `resource_engine.py`, `deck_validator.py`, `battle_manager.py` | 战斗逻辑 |
| **集成** | `feishu_client.py`, `base_sync.py`, `webhook_handler.py` | 外部系统 |
| **入口** | `main.py` | FastAPI路由 + HTML页面 |

---

## 6. 飞书 Base 集成状态

| 项目 | 值 |
|------|-----|
| Base Token | `CB6XbtkLaafJnYsDL8RcHFpEnDg` |
| 表数量 | 8个 |
| Workflow 数量 | 3个 (2个启用，1个 SetRecordTrigger 待验证) |
| 读写状态 | 读正常，写权限已配置但写入流程调试中 |

---

## 7. 已知问题速查

| ID | 问题 | 位置 |
|----|------|------|
| C1 | Combat_Constitution 与 V6 代码冲突 | `.claude/skills/Combat_Constitution.md` |
| C2 | 5个 memory 引用已删除文件 | `memory/*.md` |
| C3 | 2套重复 memory 目录 | `.claude/projects/` vs `C:\Users\Gao\.claude\` |
| C4 | ~47个文件从磁盘删除但未 git rm | `docs/NPC/*`, `docs/设计笔记/*` |
| C5 | spark 子模块与主版本重复 (9/11文件一致) | `battle-judge/battle-judge-spark/` |
| C6 | main.py 中 HTML 混合在 Python 字符串 | `battle-judge/main.py:83-247` |
| C7 | README.md 称 V2 为当前版本 | `docs/combat/README.md` |
| C8 | 蛾飞升 Lv14 vs Lv15 冲突 | `Current_Narrative_Foundation.md` vs `ascension-rules.md` |
| C9 | 根目录 7 个垃圾文件 | `wf_*.json`, `docs.zip`, `auth_qrcode.png`, `structure.txt` |
| C10 | render.yaml 引用即将被删除的 npc/spark 路径 | `render.yaml` |
