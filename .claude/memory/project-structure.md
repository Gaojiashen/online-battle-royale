---
name: project-structure
description: 项目文件结构（2026-07-10 Phase 2 重构后）
metadata: 
  node_type: memory
  type: project
  originSessionId: 8eb9ccbc-e2ff-4e9e-8ab0-81e810ff72df
---

## 当前文件结构（2026-07-10 Phase 2 重构后）

```
D:\vibecoding\onling-battle-royale\
│
├── src/judge/                            # 战斗裁判引擎
│   ├── app.py                            # FastAPI 入口 + lifespan + /health
│   ├── models/
│   │   ├── requests.py                   # Pydantic 请求模型（5类）
│   │   └── responses.py                  # Pydantic 响应模型（8类）
│   ├── engine/
│   │   ├── card_library.py               # 48张V6卡牌定义
│   │   ├── rps_resolver.py               # RPS核心结算引擎
│   │   ├── resource_engine.py            # 六性相资源系统
│   │   ├── deck_validator.py             # 可用牌计算+牌库校验
│   │   └── battle_manager.py             # 对战生命周期管理（内存）
│   ├── integration/
│   │   ├── feishu_client.py              # 飞书 BitTable API 客户端
│   │   └── base_sync.py                  # Base 数据同步
│   ├── routes/
│   │   ├── battle.py                     # 7个对战API端点
│   │   ├── judge_panel.py               # /judge + /api/judge/pending
│   │   └── webhook.py                   # Webhook处理器
│   ├── templates/
│   │   └── judge_panel.html              # 法官面板HTML
│   ├── tests/
│   │   └── test_battle_scenarios.py     # 8个测试场景
│   └── requirements.txt                  # fastapi uvicorn httpx pydantic
│
├── docs/                                 # 设计文档
│   ├── design/                           # 活跃游戏设计文档
│   │   ├── world-setting.md              # 核心世界观
│   │   ├── map-regions.md                # 28区地图+连接
│   │   ├── map-edinburgh.svg             # 地图SVG
│   │   ├── main-narrative.md             # 主线剧情（Day 20末日+轮回）
│   │   └── npc-sebastian-croft.md        # 塞巴斯蒂安·克罗夫特（NPC角色卡）
│   ├── combat/                           # 战斗系统
│   │   ├── README.md                     # V6已更新
│   │   ├── generate_cards_v6.py          # V6卡牌Excel生成脚本
│   │   └── 牌组/
│   │       └── 战斗牌组_v6.xlsx           # V6卡牌数据（当前版本）
│   ├── archive/                          # 归档
│   │   ├── combat-v2/                    # V2参考文件（6个MD）
│   │   └── combat-v4-v5/                # V4/V5设计文档+旧Excel+V5脚本
│   ├── operations/                       # 运维文档
│   │   └── feishu_install_guidance.md
│   ├── before-refactor-state.md          # 重构前状态快照
│   └── project-refactoring-plan.md      # 重构计划
│
├── scripts/                              # 工具脚本
│   ├── generate_items_excel.py           # 道具搜索池Excel生成
│   └── 道具与搜索池.xlsx                 # 道具数据
│
├── .claude/                              # Claude Code 配置
│   ├── settings.local.json
│   └── skills/
│       ├── Combat_Constitution.md
│       ├── NPC_Design_Constitution.md
│       └── Project_Constitution.md
│
├── render.yaml                           # Render 部署（单服务：judge）
└── .gitignore
```

## 重构历史

> **2026-07-10 Phase 2**：`battle-judge/` → `src/judge/` 模块化拆分
> - 拆 main.py（521行）→ app.py + routes/battle.py + routes/judge_panel.py
> - 拆 models.py → models/requests.py + responses.py + __init__.py（重导出）
> - 提取 inline HTML → templates/judge_panel.html
> - engine/integration/routes/models 四层清晰分离
> - webhook_handler → routes/webhook.py
> - 所有 import 路径更新
> - render.yaml 路径同步更新

> **2026-07-10 Phase 1**：清理废弃代码和文档
> - 废弃 `tools/npc_tracker/`（功能迁移至飞书 Base）
> - 废弃 `data/`（早期原型）
> - 删除 `battle-judge/battle-judge-spark/`（gitlink残留）
> - 整理 docs/ 为 design/combat/archive/operations 四区
> - 新建 scripts/ 收纳数据生成工具
> - 清理根目录临时文件（wf_*.json等）

## 关键路径

- 裁判服务：`src/judge/app.py`
- 卡牌数据：`src/judge/engine/card_library.py`
- 世界观：`docs/design/world-setting.md`
- 地图：`docs/design/map-regions.md`
- 重构前快照：`docs/before-refactor-state.md`
- 重构计划：`docs/project-refactoring-plan.md`
