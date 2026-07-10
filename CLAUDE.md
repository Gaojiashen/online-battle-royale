# CLAUDE.md

## Memory 存储位置

本项目的记忆文件存储在项目内的 `.claude/memory/` 目录中，**不使用** C 盘用户目录下的 memory 存储。

## 上下文恢复

每次运行时，读取 `.claude/memory/MEMORY.md` 索引文件，并按需加载 `.claude/memory/` 中的相关记忆文件来恢复项目上下文。

## 项目概述

密教模拟器S2 — 在线大逃杀游戏。核心模块：战斗裁判引擎（`src/judge/`），部署于 Render.com。
