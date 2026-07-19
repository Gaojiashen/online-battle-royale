-- 001_init.sql — 密教模拟器 S2 初始 PostgreSQL Schema
-- Phase 5.0: Feishu Base → PostgreSQL 迁移

BEGIN;

-- ═══════════════════════════════════════════════════════
-- 1. players — 玩家帐号数据
-- 替代 Feishu TABLE_PLAYERS (tbl4KaRcfiz1pZq1)
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS players (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,
    -- 六性相等级
    lantern         INTEGER NOT NULL DEFAULT 0,   -- 灯
    moth            INTEGER NOT NULL DEFAULT 0,   -- 蛾
    forge           INTEGER NOT NULL DEFAULT 0,   -- 铸
    winter          INTEGER NOT NULL DEFAULT 0,   -- 冬
    heart           INTEGER NOT NULL DEFAULT 0,   -- 心
    blade           INTEGER NOT NULL DEFAULT 0,   -- 刃
    game_hp         INTEGER NOT NULL DEFAULT 100, -- 游戏 HP（非战斗 HP）
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_name ON players (name);


-- ═══════════════════════════════════════════════════════
-- 2. battles — 对战管理
-- 替代 Feishu TABLE_BATTLE (tblWciOhRlFFEaSr)
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS battles (
    id              SERIAL PRIMARY KEY,
    battle_id       VARCHAR(8) NOT NULL,
    player_a_name   VARCHAR(64) NOT NULL,
    player_b_name   VARCHAR(64) NOT NULL,
    player_a_aspects JSONB NOT NULL DEFAULT '{}',  -- {"灯":4,"蛾":6,...}
    player_b_aspects JSONB NOT NULL DEFAULT '{}',
    state           VARCHAR(32) NOT NULL DEFAULT 'initialized',
    current_round   INTEGER NOT NULL DEFAULT 0,
    winner          VARCHAR(64),
    end_reason      TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_battles_battle_id ON battles (battle_id);
CREATE INDEX IF NOT EXISTS idx_battles_state       ON battles (state);
CREATE INDEX IF NOT EXISTS idx_battles_player_a    ON battles (player_a_name);
CREATE INDEX IF NOT EXISTS idx_battles_player_b    ON battles (player_b_name);
CREATE INDEX IF NOT EXISTS idx_battles_created     ON battles (created_at);


-- ═══════════════════════════════════════════════════════
-- 3. battle_players — 玩家战斗状态（每场对战 2 行）
-- 替代 Feishu TABLE_PLAYER_STATE (tblTNAkesS7WlJoR)
-- deck_slots 使用 JSONB 数组存储卡牌 ID，替代牌位1-8
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS battle_players (
    id              SERIAL PRIMARY KEY,
    battle_id       VARCHAR(8) NOT NULL REFERENCES battles(battle_id) ON DELETE CASCADE,
    side            CHAR(1) NOT NULL CHECK (side IN ('A', 'B')),
    player_name     VARCHAR(64) NOT NULL,
    -- 战斗状态
    hp              INTEGER NOT NULL DEFAULT 20,
    max_hp          INTEGER NOT NULL DEFAULT 20,
    -- 六资源
    edge            INTEGER NOT NULL DEFAULT 0,   -- 锋芒 0-3
    phantom         INTEGER NOT NULL DEFAULT 0,   -- 幻影 0-3
    charge          INTEGER NOT NULL DEFAULT 0,   -- 蓄力 0-3
    chill           INTEGER NOT NULL DEFAULT 0,   -- 寒意 0-3
    pulse           INTEGER NOT NULL DEFAULT 0,   -- 脉动 0-4
    read            INTEGER NOT NULL DEFAULT 0,   -- 洞悉 0-2
    insight         INTEGER NOT NULL DEFAULT 0,   -- 看破 0-2
    -- 牌库（JSONB 数组，如 ["B01","B02","M01",...]）
    deck_slots      JSONB NOT NULL DEFAULT '[]'::jsonb,
    deck_confirmed  BOOLEAN NOT NULL DEFAULT FALSE,
    submitted       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bp_battle_side ON battle_players (battle_id, side);
CREATE INDEX IF NOT EXISTS idx_bp_player        ON battle_players (player_name);


-- ═══════════════════════════════════════════════════════
-- 4. battle_rounds — 回合记录
-- 替代 Feishu TABLE_BATTLE_LOG (tblyUL90LNC1Snb5)
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS battle_rounds (
    id              SERIAL PRIMARY KEY,
    battle_id       VARCHAR(8) NOT NULL REFERENCES battles(battle_id) ON DELETE CASCADE,
    round_number    INTEGER NOT NULL,
    -- 双方出牌
    card_a_id       VARCHAR(8),
    card_a_name     VARCHAR(32),
    card_b_id       VARCHAR(8),
    card_b_name     VARCHAR(32),
    -- RPS 结算
    rps_description TEXT,
    damage_to_a     INTEGER NOT NULL DEFAULT 0,
    damage_to_b     INTEGER NOT NULL DEFAULT 0,
    hp_a_after      INTEGER,
    hp_b_after      INTEGER,
    -- 特殊事件
    special_events  TEXT[] DEFAULT '{}',
    winner_side     CHAR(1),
    -- 完整状态快照（JSONB — 每个玩家的 BattleState 序列化）
    state_a_snapshot JSONB,
    state_b_snapshot JSONB,
    -- 资源变更日志
    resource_logs_a TEXT[] DEFAULT '{}',
    resource_logs_b TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_br_battle_round ON battle_rounds (battle_id, round_number);


-- ═══════════════════════════════════════════════════════
-- 5. battle_submissions — 回合提交记录
-- 替代 Feishu TABLE_SUBMISSION (tblcmGlzO76H3RQt)
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS battle_submissions (
    id              SERIAL PRIMARY KEY,
    battle_id       VARCHAR(8) NOT NULL REFERENCES battles(battle_id) ON DELETE CASCADE,
    side            CHAR(1) NOT NULL,
    player_name     VARCHAR(64) NOT NULL,
    card_id         VARCHAR(8) NOT NULL,
    round_number    INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bs_battle_side_round ON battle_submissions (battle_id, side, round_number);
CREATE INDEX IF NOT EXISTS idx_bs_player             ON battle_submissions (player_name);


COMMIT;
