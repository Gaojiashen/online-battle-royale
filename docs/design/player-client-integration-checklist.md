# 玩家客户端集成测试准备清单

> 生成时间：2026-07-10 | 基于 `src/judge/` 全部代码路径分析

---

## 一、环境变量

### 生产 / 本地都必需的变量

| 变量 | 用途 | 影响范围 | 设置位置 |
|------|------|------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID | 全局：未设置则 Base 同步全部跳过 | Render env / shell |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret | 获取 tenant_access_token 必需 | Render env / shell |
| `PORT` | 监听端口 | Render 自动注入（本地默认 8080） | 自动 |

### 可选变量（已有默认值，无需手动设置）

| 变量 | 默认值 | 用途 |
|------|------|------|
| `FEISHU_BASE_TOKEN` | `CB6XbtkLaafJnYsDL8RcHFpEnDg` | 飞书 Base token |
| `TABLE_PLAYERS` | `tbl4KaRcfiz1pZq1` | 玩家表 ID |
| `TABLE_BATTLE` | `tblWciOhRlFFEaSr` | 对战管理表 ID |
| `TABLE_PLAYER_STATE` | `tblTNAkesS7WlJoR` | 玩家战斗状态表 ID |
| `TABLE_AVAILABLE` | `tbl0DDzK6ckrqQah` | 玩家可用牌表 ID |
| `TABLE_BATTLE_LOG` | `tblyUL90LNC1Snb5` | 对战记录表 ID |
| `TABLE_SUBMISSION` | `tblcmGlzO76H3RQt` | 回合提交表 ID |

### 本地开发配置

```bash
# 在 shell 或 .env 中设置（不提交到 git）
export FEISHU_APP_ID="cli_xxxxxxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export FEISHU_BASE_TOKEN="CB6XbtkLaafJnYsDL8RcHFpEnDg"
```

---

## 二、飞书 Base 表要求

### 概览

玩家客户端使用 **7 张表**（全部已存在，无需新建）：

```
Base: 战斗玩家面板 (CB6XbtkLaafJnYsDL8RcHFpEnDg)

  tbl4KaRcfiz1pZq1  玩家                  (只读，查性相等级)
  tbl1NnOpplq3x7Rg  玩家(备选)             (只读，备选性相来源)
  tblWciOhRlFFEaSr  对战管理               (读写，战斗状态)
  tblTNAkesS7WlJoR  玩家战斗状态            (读写，HP/资源/牌位)
  tbl0DDzK6ckrqQah  玩家可用牌              (读写，可用卡牌列表)
  tblyUL90LNC1Snb5  对战记录               (只读，回合日志)
  tblcmGlzO76H3RQt  回合提交               (读写，出牌记录)
  tblbheflCQ2wTgml  法官面板               (写，回写对战ID)
```

---

### 表 1/2：玩家（`tbl4KaRcfiz1pZq1` / `tbl1NnOpplq3x7Rg`）

**只读。** 玩家名 → 性相等级映射。`player_service.lookup_player` 两张表都查。

#### 必需字段（tbl4KaRcfiz1pZq1）

| 字段名 | 类型 | 用途 | 备注 |
|------|------|------|------|
| `玩家名称` | 文本 | 匹配玩家名 | ⚠️ 字段名必须是 `玩家名称` |
| `灯` | 数字 | 灯性相等级 | 0-15 |
| `蛾` | 数字 | 蛾性相等级 | |
| `铸` | 数字 | 铸性相等级 | |
| `冬` | 数字 | 冬性相等级 | |
| `心` | 数字 | 心性相等级 | |
| `刃` | 数字 | 刃性相等级 | |
| `游戏HP` | 数字 | 玩家游戏 HP | |

#### 必需字段（tbl1NnOpplq3x7Rg，备选）

| 字段名 | 类型 | 用途 | 备注 |
|------|------|------|------|
| `名称` | 文本 | 匹配玩家名 | ⚠️ 字段名必须是 `名称` |
| `灯` ～ `刃` | 数字 | 六性相等级 | 同上 |

> ⚠️ 两张表的字段名不同（`玩家名称` vs `名称`）。如果现有一张表已有数据，只需保证那张表字段齐全。代码会两张表都尝试。

#### 测试数据要求

至少 2 条记录：

```
玩家名称: 高   灯:4 蛾:6 铸:2 冬:2 心:3 刃:5  游戏HP:82
玩家名称: 橙子  灯:6 蛾:4 铸:3 冬:5 心:2 刃:2  游戏HP:78
```

---

### 表 3：对战管理（`tblWciOhRlFFEaSr`）

**读写。** 每行 = 一场战斗。法官面板发起时创建。

#### 必需字段

| 字段名 | 类型 | 写/读 | 用途 |
|------|------|------|------|
| `对战ID` | 文本 | 写 + 读 | 唯一标识 |
| `玩家A名称` | 文本 | 写 + 读 | A 玩家名 |
| `玩家B名称` | 文本 | 写 + 读 | B 玩家名 |
| `玩家A性相等级` | 文本 | 写 | JSON 字符串 `{"灯":4,"蛾":6}` |
| `玩家B性相等级` | 文本 | 写 | JSON 字符串 |
| `状态` | 单选 | 写 + 读 | 选项：`已初始化` / `选牌中` / `对战中` / `已结束` |
| `当前回合` | 数字 | 写 + 读 | 0 = 未开始 |
| `胜者` | 文本 | 写 + 读 | 结束时填写 |
| `创建时间` | 文本 | 写 | `YYYY-MM-DD HH:mm:ss` |

> ⚠️ 单选字段 `状态` 的选项必须包含以上 4 个值。现有表已有这些选项。

#### 自动写入时机

| 操作 | 写入字段 |
|------|------|
| `init-from-base` | 全部初始字段 |
| `confirm_deck`（双方确认牌库） | `状态`→对战中, `当前回合`→1 |
| 战斗结束 | `状态`→已结束, `胜者`, `当前回合` |

---

### 表 4：玩家战斗状态（`tblTNAkesS7WlJoR`）

**读写。** 每场战斗 2 行（A + B）。最复杂的表。

#### 必需字段

| 字段名 | 类型 | 写/读 | 用途 |
|------|------|------|------|
| `对战ID` | 文本 | 写 + 读 | 关联战斗 |
| `玩家侧` | 单选 | 写 + 读 | 选项：`A` / `B` |
| `玩家名称` | 文本 | 写 + 读 | |
| `战HP` | 数字 | 写 + 读 | 0-20 |
| `锋芒` | 数字 | 写 + 读 | 刃资源 0-3 |
| `幻影` | 数字 | 写 + 读 | 蛾资源 0-3 |
| `蓄力` | 数字 | 写 + 读 | 铸资源 0-3 |
| `寒意` | 数字 | 写 + 读 | 冬资源 0-3 |
| `脉动` | 数字 | 写 + 读 | 心资源 0-4 |
| `洞悉` | 数字 | 写 + 读 | 灯资源 0-2 |
| `看破` | 数字 | 写 + 读 | 通用资源 0-2 |
| `已提交` | 复选框 | 写 + 读 | 本回合是否已提交 |
| `牌库已确认` | 复选框 | 写 + 读 | 8 张牌已选定 |
| `牌位1` ～ `牌位8` | 文本 | 写 + 读 | 卡牌 ID（如 `C01`） |

> ⚠️ `牌位1-8` 各 8 个独立文本字段。现有表已有。

#### 自动写入时机

| 操作 | 写入字段 |
|------|------|
| `sync_battle_init` | 对战ID, 玩家侧, 玩家名称, HP=20, 六资源=0, 看破=0, 已提交=false |
| `_update_player_state`（每回合结算后） | 战HP, 六资源, 看破, 已提交=false |
| `sync_deck_confirmed`（玩家确认牌库） | 牌位1-8, 牌库已确认=true |
| `_set_submitted_flag` | 已提交 |

---

### 表 5：玩家可用牌（`tbl0DDzK6ckrqQah`）

**读写。** 每个玩家每场战斗多行（可变数量，取决于性相等级）。

#### 必需字段

| 字段名 | 类型 | 写/读 | 用途 |
|------|------|------|------|
| `对战ID` | 文本 | 写 + 读 | 过滤条件 |
| `玩家侧` | 单选 | 写 + 读 | 选项：`A` / `B` |
| `卡牌ID` | 文本 | 写 + 读 | 如 `C01` / `B03` |
| `卡牌名称` | 文本 | 写 + 读 | 如 "挥击" |
| `类别` | 文本 | 写 + 读 | 进攻/防御/佯攻/打断/状态 |
| `性相` | 文本 | 写 + 读 | 刃/蛾/铸/冬/心/灯/通用 |

> ⚠️ **关键**：`init-from-base` 现在（Fix 4 修复后）会调用 `sync_available_cards` 自动填充此表。每场战斗 2 × N 行（N = 每方可用的卡牌数，通常 10-20 张）。

#### 测试数据要求

无需手动准备。`init-from-base` 会自动创建。

---

### 表 6：对战记录（`tblyUL90LNC1Snb5`）

**只读（玩家客户端视角）。** 每行 = 一个已结算回合。`sync_round_result` 写入。

#### 必需字段

| 字段名 | 类型 | 写/读 | 用途 |
|------|------|------|------|
| `对战ID` | 文本 | 写 + 读 | 过滤条件 |
| `回合编号` | 数字 | 写 + 读 | |
| `A使用卡牌` | 文本 | 写 + 读 | |
| `B使用卡牌` | 文本 | 写 + 读 | |
| `RPS结果描述` | 文本 | 写 + 读 | 如 "A攻击被B防御减免" |
| `A受到伤害` | 数字 | 写 + 读 | |
| `B受到伤害` | 数字 | 写 + 读 | |
| `A剩余HP` | 数字 | 写 + 读 | |
| `B剩余HP` | 数字 | 写 + 读 | |
| `特殊事件` | 文本 | 写 | 分号分隔的事件列表 |
| `胜者` | 文本 | 写 | 最终回合填写 |

#### 自动写入时机

每回合结算后由 `sync_round_result` 写入。

---

### 表 7：回合提交（`tblcmGlzO76H3RQt`）

**读写。** 每行 = 一个玩家一个回合的出牌。

#### 必需字段

| 字段名 | 类型 | 写/读 | 用途 |
|------|------|------|------|
| `对战ID` | 文本 | 写 + 读 | |
| `玩家侧` | 单选 | 写 + 读 | 选项：`A` / `B` |
| `玩家名称` | 文本 | 写 + 读 | |
| `回合编号` | 数字 | ⚠️ 读但未写 | 用于检查已提交 |
| `选择的卡牌ID` | 文本 | 写 | |
| `提交时间` | 文本 | 写 | `HH:mm:ss` |

> ⚠️ **已知问题**：`sync_submission_made` 写入时**不包含 `回合编号`**。`_has_submitted_this_round` 依赖此字段做已提交检查。当前会导致页面总是显示"未提交"状态。不影响核心战斗逻辑（`battle_manager.submit_card()` 内部独立校验）。待后续修复。

---

### 表 8：法官面板（`tblbheflCQ2wTgml`）

玩家客户端**不使用**此表。法官使用。

| 字段名 | 类型 | 用途 |
|------|------|------|
| `玩家A` | 文本 | 法官填写 |
| `玩家B` | 文本 | 法官填写 |
| `状态` | 单选 | 待发起/已发起/对战中/已结束 |
| `对战ID` | 文本 | `init-from-base` 回写 |

---

## 三、Base 表配置汇总

```
Base: 战斗玩家面板
Token: CB6XbtkLaafJnYsDL8RcHFpEnDg
URL: https://acn5j59fiukt.feishu.cn/base/CB6XbtkLaafJnYsDL8RcHFpEnDg

Checklist:
  ☐ 表1 (tbl4KaRcfiz1pZq1): 玩家名称 + 六性相 + 游戏HP — 至少2条测试数据
  ☐ 表2 (tbl1NnOpplq3x7Rg): 名称 + 六性相 — 有数据则可，无数据不阻塞
  ☐ 表3 (tblWciOhRlFFEaSr): 对战管理 — 字段齐全，状态选项正确
  ☐ 表4 (tblTNAkesS7WlJoR): 玩家战斗状态 — 22个字段齐全，含牌位1-8 + 牌库已确认
  ☐ 表5 (tbl0DDzK6ckrqQah): 玩家可用牌 — 字段齐全
  ☐ 表6 (tblyUL90LNC1Snb5): 对战记录 — 字段齐全
  ☐ 表7 (tblcmGlzO76H3RQt): 回合提交 — 字段齐全，含回合编号
  ☐ 表8 (tblbheflCQ2wTgml): 法官面板 — 字段齐全
  ☐ 飞书应用: FEISHU_APP_ID + FEISHU_APP_SECRET 已配置
  ☐ 飞书应用权限: bitable 读写 scope 已授权
```

---

## 四、已知配置不一致项

| # | 问题 | 影响 | 优先级 |
|------|------|------|------|
| K1 | `玩家` 表有两张（`tbl4KaRcfiz1pZq1` 字段 `玩家名称`、`tbl1NnOpplq3x7Rg` 字段 `名称`）| 代码兼容双表，不阻塞 | 信息 |
| K2 | `sync_submission_made` 不写入 `回合编号` | 页面"已提交"状态显示不准 | 🟡 待修复 |
| K3 | `sync_battle_init` 历史参数 bug（传入 req/result 对象而非 player_name 字符串）| Fix 4 已修正 | ✅ 已修复 |

---

## 五、最小可运行测试步骤

### 前提

- ✅ Base 中有「高」和「橙子」两个玩家记录（表1 或 表2）
- ✅ 法官面板表有一条「待发起」记录（A=高, B=橙子）
- ✅ 服务已部署（Render 或 `uvicorn app:app`）
- ✅ `FEISHU_APP_ID` + `FEISHU_APP_SECRET` 已配置

### 测试步骤

```
Step 1: 法官发起战斗
  打开 /judge → 找到「高 vs 橙子」→ 点击「发起对战」
  预期: 对战管理新增 1 行; 玩家战斗状态新增 2 行; 玩家可用牌新增 N 行

Step 2: 验证 Base 数据
  对战管理: 状态=已初始化, 当前回合=0
  玩家战斗状态: 高/A HP=20, 橙子/B HP=20
  玩家可用牌: 高/A 有 N 张卡牌, 橙子/B 有 M 张卡牌

Step 3: A 打开 /player
  输入"高"→ 进入战斗
  curl -s http://localhost:8080/api/player/lookup?name=高
  预期: {"ok":true, "has_battle":true, "battle_id":"..."}

Step 4: A 查看可用卡牌
  curl -s http://localhost:8080/api/player/高/available-cards
  预期: {"ok":true, "cards":[...], "selected_count":0, "deck_locked":false}

Step 5: A 选 8 张牌
  curl -s -X POST http://localhost:8080/api/player/select-deck \
    -H 'Content-Type: application/json' \
    -d '{"player_name":"高","battle_id":"<ID>","card_ids":["C01","C02","C03","C04","C05","C06","B01","B02"]}'
  预期: {"ok":true, "status":"waiting_for_opponent"}

Step 6: B 选 8 张牌
  curl -s -X POST http://localhost:8080/api/player/select-deck \
    -H 'Content-Type: application/json' \
    -d '{"player_name":"橙子","battle_id":"<ID>","card_ids":["C01","C02","C03","C04","C05","C06","M01","M02"]}'
  预期: {"ok":true, "status":"battle_started", "current_round":1}

Step 7: A 查看战斗状态
  curl -s http://localhost:8080/api/player/高/battle
  预期: {"ok":true, "state":"对战中", "current_round":1, "my_hp":20}

Step 8: A 提交第 1 回合出牌
  curl -s -X POST http://localhost:8080/api/player/submit-card \
    -H 'Content-Type: application/json' \
    -d '{"player_name":"高","battle_id":"<ID>","round_number":1,"card_id":"C01"}'
  预期: {"ok":true, "status":"waiting_for_opponent"}

Step 9: B 提交第 1 回合出牌
  curl -s -X POST http://localhost:8080/api/player/submit-card \
    -H 'Content-Type: application/json' \
    -d '{"player_name":"橙子","battle_id":"<ID>","round_number":1,"card_id":"M01"}'
  预期: {"ok":true, "status":"resolved", "result":{...}}

Step 10: A 查看战斗日志
  curl -s http://localhost:8080/api/player/高/battle-logs
  预期: {"ok":true, "logs":[{"round":1, "my_card":"挥击", ...}]}

Step 11: 重复 Step 8-10 直到一方 HP≤0 → 战斗结束
  预期: /api/player/高/battle 返回 state=已结束, winner=...
```

### 快速冒烟测试（单次 shell）

```bash
# 前提：替换 <BATTLE_ID> 为 init-from-base 返回的实际值
B=<BATTLE_ID>

# 1. lookup
curl -s http://localhost:8080/api/player/lookup?name=高 | python -m json.tool

# 2. battle
curl -s http://localhost:8080/api/player/高/battle | python -m json.tool

# 3. cards
curl -s http://localhost:8080/api/player/高/available-cards | python -m json.tool | head -20

# 4. select deck (用前 8 张可用卡牌)
curl -s -X POST http://localhost:8080/api/player/select-deck \
  -H 'Content-Type: application/json' \
  -d "{\"player_name\":\"高\",\"battle_id\":\"$B\",\"card_ids\":[\"C01\",\"C02\",\"C03\",\"C04\",\"C05\",\"C06\",\"B01\",\"B02\"]}"

# 5. submit
curl -s -X POST http://localhost:8080/api/player/submit-card \
  -H 'Content-Type: application/json' \
  -d "{\"player_name\":\"高\",\"battle_id\":\"$B\",\"round_number\":1,\"card_id\":\"C01\"}"

# 6. logs
curl -s http://localhost:8080/api/player/高/battle-logs | python -m json.tool
```
