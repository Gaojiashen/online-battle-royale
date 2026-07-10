---
name: player-panel
description: 法官辅助应用的玩家模拟面板（Player Panel）完整设计与实现
metadata: 
  node_type: memory
  type: project
  originSessionId: cc6e16bc-6f25-4f64-84fb-3d908b2d19f6
---

## 概述

> **NPC Tracker 已于 2026-07-09 废弃，玩家面板功能迁移至飞书 Base。** 原始代码 `tools/npc_tracker/` 及其所有子文件已从仓库删除。玩家状态、对战管理等功能现在通过飞书多维表格和 `src/judge/` 战斗裁判引擎实现。以下为历史参考内容。

2026-06-30 在 `tools/npc_tracker/` 中实现了完整的玩家模拟操作面板。入口：`/player/{id}/panel`。

## 核心功能

### 时间系统
- 初始 Day 1, 08:00 (480分钟)
- 时段：☀️白天(8-20) / 🌙夜晚(20-22) / 💤深夜(22-8)
- 行动消耗时间：探索0.5h、移动0.5-2h、交谈/交易0.5h、说服/威胁1h、招募2h
- 超过22:00自动跨日，重置到次日08:00
- 数据库：`players.game_day` (INT), `players.game_time` (INT, 分钟)

### 移动系统
- 下拉选择相邻区域（显示区域编号、名称、耗时）
- 快速移动：点击相邻区域列表直接出发
- 移动耗时从 `location_connections.travel_time` 读取
- 远距离移动(≥1h)自动扣除少量车马费

### 探索系统
- 每个区域可执行"探索"（0.5h）
- 随机结果（1d20）：大失败(1-3)/普通(4-10)/良好(11-17)/大成功(18-20)
- 道具系统未设计，结果以金币占位（5-50G随机）

### NPC交互
- 普通交互：💬交谈 🤝交易 🗣️说服 ⚡威胁 🤲招募（通用随机结果）
- 剧情线交互：有剧情线的NPC显示金色「📜 剧情线」按钮
- 弹出剧情线弹窗：场景描述 + 选项A/B/C + 选择后显示结果
- 自动推进NPC剧情节点、消耗时间、记录行动日志

### NPC位置智能过滤（关键设计）
- 有剧情线的NPC：**只在当前未完成节点所在区域出现**（不再全城游荡）
- 无剧情线的NPC：按原始location字段匹配（保持原逻辑）
- 节点location格式：`{区域编号}{地名}`（如 `③图书馆 主厅`）
- 无法解析区域编号的特殊节点（如 `玩家住处`）：回退到NPC原始location
- NPC卡片显示当前节点编号和节点位置

### 剧情节点前置校验
- 地点校验：节点location必须匹配玩家当前位置，否则弹窗警告
- 时间校验：从hint字段解析触发时间（如 "下午5:00"），不匹配时警告
- 警告不阻止法官操作（可强制推进）

### 已解锁地图
- 移动时自动发现目标区域及其所有相邻区域
- 数据库：`players.discovered_locations` (JSON数组)
- 左侧面板展示：按6个区域分组，📍当前/✅已解锁/🔒未探索
- 显示已知道路数（↔N路）和进度统计（已解锁数/总数）

### 复制玩家状态
- 顶栏「📋 复制状态」按钮，一键复制格式化文本到剪贴板

## 数据库新增

- `players.game_day` (INT DEFAULT 1)
- `players.game_time` (INT DEFAULT 480)
- `players.discovered_locations` (TEXT DEFAULT '[]')
- `locations` 表（27个区域 + 描述）
- `location_connections` 表（区域连接 + 旅行耗时）

## API新增

| 路由 | 说明 |
|------|------|
| `GET /player/{id}/panel` | 玩家面板页面 |
| `POST /api/player/{id}/move` | 移动（含自动发现） |
| `POST /api/player/{id}/explore` | 探索（随机金币） |
| `POST /api/player/{id}/socialize` | NPC交互（通用） |
| `GET /api/npc/{id}/storyline-current?player_id=` | 获取当前剧情节点+选项 |
| `POST /api/npc/{id}/player-choose` | 玩家选择选项→推进剧情+时间 |
| `GET /api/player/{id}/map` | 已解锁地图数据 |
| `GET /api/player/{id}/time-info` | 时间/时段信息 |

## 数据状态

> **NPC Tracker 已于 2026-07-09 废弃。** 玩家面板功能迁移至飞书 Base（`CB6XbtkLaafJnYsDL8RcHFpEnDg`），所有玩家状态、NPC交互、对战流程改为 Base + 战斗裁判 API 管理。`tools/npc_tracker/` 将在 Phase 1 重构中删除。

## 已修复的种子数据问题

（历史记录——相关文件已在重构中删除）
- 伊索贝尔节点7: `"牛门·第三个井盖"` → `"⑩牛门·第三个井盖"`
- 邓肯节点4: `"利斯路入口"` → `"㉖利斯路入口"`
- 伊索贝尔节点6 `"玩家住处"` 为特殊叙事节点，代码已做fallback

## 关键文件（已废弃）

- `tools/npc_tracker/main.py` — 路由和API（已废弃）
- `tools/npc_tracker/database.py` — 数据库schema、种子数据（已废弃）
- `tools/npc_tracker/templates/player_panel.html` — 面板前端（已废弃）
