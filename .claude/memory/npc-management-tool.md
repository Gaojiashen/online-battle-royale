---
name: npc-management-tool
description: NPC剧情线管理工具的架构与功能记录
metadata: 
  node_type: memory
  type: project
  originSessionId: d8afed41-c9e1-46e7-986b-2ec73ebde215
---

## 位置
`tools/npc_tracker/` — FastAPI + SQLite + WebSocket 的Web应用

## 架构
- **后端**：FastAPI，SQLite 存数据，WebSocket 实时同步
- **前端**：Jinja2 服务端渲染，暗色哥特风UI，vanilla JS
- **部署**：计划部署到 Render 免费云服务，两个法官浏览器访问

## 已实现功能
- 6个NPC总览看板（卡片网格）
- 伊索贝尔7节点剧情线（完整场景描述+选项面板）
- 法官工作流：复制场景→玩家选→点选项→复制结果→继续下一节点
- 锁状态管理（无主/锁定/完结/终结）
- NPC状态切换（alive/injured/dead/missing）
- 节点回退
- 法官笔记
- 事件日志（自动记录）

## 关键决策
- 不打包成EXE，改为部署到云端，两人浏览器访问
- 云端部署暂缓，等所有功能做完再部署
- NPC剧情线编写规范已写入 `tools/npc_tracker/NPC剧情线编写规范.md`

## 状态

> **已废弃（2026-07-09）。** NPC 追踪器功能已迁移至飞书 Base（`CB6XbtkLaafJnYsDL8RcHFpEnDg`），由战斗裁判引擎统一管理。`tools/npc_tracker/` 代码即将在重构中删除，git 历史保留可恢复。

## 待办（历史）
- 所有功能做完后部署到 Render 云端（未执行）
- 可能用 Turso 做云端持久化数据库（未执行）
