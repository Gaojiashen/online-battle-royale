"""
Phase 5.1 最小验证测试 — PostgreSQL 持久化层。

测试内容：
1. 数据库连接
2. Migration 执行
3. PostgresSync 方法调用
"""

import os
import sys
import json
import asyncio
import asyncpg

# 确保 src/judge 在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integration.postgres_sync import PostgresSync

# ════════════════════════════════════════════════════
# 配置 — 使用本地 PostgreSQL
# ════════════════════════════════════════════════════

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)

TEST_BATTLE_ID = "test0001"


async def _run_migration(pool: asyncpg.Pool):
    """执行 migration SQL"""
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "migrations", "001_init.sql",
    )
    with open(migration_path, "r", encoding="utf-8") as f:
        sql = f.read()

    async with pool.acquire() as conn:
        await conn.execute(sql)

    print("✓ Migration 001_init.sql 执行成功")


async def _cleanup(pool: asyncpg.Pool):
    """清理测试数据"""
    tables = [
        "battle_submissions",
        "battle_rounds",
        "battle_players",
        "battles",
        "players",
    ]
    async with pool.acquire() as conn:
        for t in tables:
            await conn.execute(f"DELETE FROM {t}")


async def test_connection():
    """测试数据库连接"""
    pool = await asyncpg.create_pool(dsn=TEST_DB_URL, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
        print(f"✓ 数据库连接成功: {version.split(',')[0]}")
    finally:
        await pool.close()


async def test_migration():
    """测试 migration 执行"""
    pool = await asyncpg.create_pool(dsn=TEST_DB_URL, min_size=1, max_size=2)
    try:
        await _run_migration(pool)
    finally:
        await pool.close()


async def test_postgres_sync():
    """测试 PostgresSync 核心方法"""
    pool = await asyncpg.create_pool(dsn=TEST_DB_URL, min_size=1, max_size=2)
    try:
        await _run_migration(pool)

        sync = PostgresSync(pool=pool)
        assert sync.enabled is True

        # ── 1. sync_battle_init ──
        await sync.sync_battle_init(
            battle_id=TEST_BATTLE_ID,
            player_a_name="测试A",
            player_b_name="测试B",
            player_a_aspects={"灯": 4, "蛾": 6},
            player_b_aspects={"铸": 5, "刃": 5},
        )

        # 验证 battles 表
        async with pool.acquire() as conn:
            battle = await conn.fetchrow(
                "SELECT * FROM battles WHERE battle_id = $1", TEST_BATTLE_ID
            )
        assert battle is not None, "battles 表应有记录"
        assert battle["state"] == "initialized"
        assert battle["player_a_name"] == "测试A"
        assert battle["player_b_aspects"] == {"铸": 5, "刃": 5}
        print(f"  ✓ sync_battle_init — battles 表 OK")

        # 验证 battle_players 表
        async with pool.acquire() as conn:
            players = await conn.fetch(
                "SELECT * FROM battle_players WHERE battle_id = $1 ORDER BY side",
                TEST_BATTLE_ID,
            )
        assert len(players) == 2, "应有 2 条 battle_players"
        assert players[0]["hp"] == 20
        assert players[0]["deck_slots"] == []
        assert players[0]["deck_confirmed"] is False
        print(f"  ✓ sync_battle_init — battle_players 表 OK")

        # ── 2. sync_battle_started ──
        await sync.sync_battle_started(battle_id=TEST_BATTLE_ID)
        async with pool.acquire() as conn:
            battle = await conn.fetchrow(
                "SELECT state, current_round FROM battles WHERE battle_id = $1",
                TEST_BATTLE_ID,
            )
        assert battle["state"] == "in_progress"
        assert battle["current_round"] == 1
        print(f"  ✓ sync_battle_started OK")

        # ── 3. sync_submission_made ──
        await sync.sync_submission_made(
            battle_id=TEST_BATTLE_ID,
            side="A",
            player_name="测试A",
            card_id="B01",
        )
        async with pool.acquire() as conn:
            sub = await conn.fetchrow(
                "SELECT * FROM battle_submissions WHERE battle_id = $1 AND side = $2",
                TEST_BATTLE_ID,
                "A",
            )
        assert sub is not None
        assert sub["card_id"] == "B01"
        print(f"  ✓ sync_submission_made OK")

        # ── 4. sync_round_result ──
        await sync.sync_round_result(
            battle_id=TEST_BATTLE_ID,
            round_number=1,
            card_a_name="B01 劈斩",
            card_b_name="M01 闪避",
            rps_description="劈斩被闪避",
            damage_to_a=0,
            damage_to_b=3,
            hp_a_after=20,
            hp_b_after=17,
            special_events=["闪避成功"],
            winner="a",
            battle_ended=False,
            state_a={"hp": 20, "edge": 1, "phantom": 0, "charge": 0, "chill": 0, "pulse": 1, "read": 0, "insight": 0},
            state_b={"hp": 17, "edge": 0, "phantom": 1, "charge": 0, "chill": 0, "pulse": 1, "read": 0, "insight": 0},
        )

        # 验证 battle_rounds
        async with pool.acquire() as conn:
            rounds = await conn.fetch(
                "SELECT * FROM battle_rounds WHERE battle_id = $1 ORDER BY round_number",
                TEST_BATTLE_ID,
            )
        assert len(rounds) == 1
        assert rounds[0]["round_number"] == 1
        assert rounds[0]["card_a_id"] == "B01"
        assert rounds[0]["damage_to_b"] == 3
        assert rounds[0]["special_events"] == ["闪避成功"]
        print(f"  ✓ sync_round_result — battle_rounds OK")

        # 验证 battle_players 资源更新
        async with pool.acquire() as conn:
            bp_a = await conn.fetchrow(
                "SELECT hp, edge, phantom FROM battle_players WHERE battle_id = $1 AND side = $2",
                TEST_BATTLE_ID, "A",
            )
        assert bp_a["hp"] == 20
        assert bp_a["edge"] == 1
        print(f"  ✓ sync_round_result — battle_players 更新 OK")

        # ── 5. sync_round_result (battle_ended) ──
        await sync.sync_round_result(
            battle_id=TEST_BATTLE_ID,
            round_number=2,
            card_a_name="B02 连斩",
            card_b_name="F01 锻甲",
            rps_description="连斩突破锻甲",
            damage_to_a=2,
            damage_to_b=5,
            hp_a_after=18,
            hp_b_after=12,
            special_events=[],
            winner="a",
            battle_ended=True,
            state_a={"hp": 18, "edge": 2, "phantom": 0, "charge": 0, "chill": 0, "pulse": 2, "read": 0, "insight": 0},
            state_b={"hp": 12, "edge": 0, "phantom": 0, "charge": 1, "chill": 0, "pulse": 2, "read": 0, "insight": 0},
        )

        async with pool.acquire() as conn:
            battle = await conn.fetchrow(
                "SELECT state, winner, current_round FROM battles WHERE battle_id = $1",
                TEST_BATTLE_ID,
            )
        assert battle["state"] == "finished"
        assert battle["winner"] == "a"
        assert battle["current_round"] == 2
        print(f"  ✓ sync_round_result (battle_ended) OK")

        # ── 6. sync_deck_confirmed + check_both_decks_confirmed ──
        # 重新初始化为 deck_selection 状态
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE battles SET state = 'deck_selection' WHERE battle_id = $1",
                TEST_BATTLE_ID,
            )

        await sync.sync_deck_confirmed(
            battle_id=TEST_BATTLE_ID, side="A", deck=["B01", "B02", "M01", "M02", "F01", "F02", "W01", "W02"],
        )
        confirmed = await sync.check_both_decks_confirmed(TEST_BATTLE_ID)
        assert confirmed is False  # 只有 A 确认

        await sync.sync_deck_confirmed(
            battle_id=TEST_BATTLE_ID, side="B", deck=["H01", "H02", "L01", "L02", "C01", "C02", "C03", "C04"],
        )
        confirmed = await sync.check_both_decks_confirmed(TEST_BATTLE_ID)
        assert confirmed is True  # 双方确认

        # 验证 deck_slots JSONB
        async with pool.acquire() as conn:
            bp_a = await conn.fetchrow(
                "SELECT deck_slots FROM battle_players WHERE battle_id = $1 AND side = $2",
                TEST_BATTLE_ID, "A",
            )
        assert len(bp_a["deck_slots"]) == 8
        assert bp_a["deck_slots"][0] == "B01"
        print(f"  ✓ sync_deck_confirmed + check_both_decks_confirmed OK")

        # ── 7. sync_available_cards（no-op 验证）──
        await sync.sync_available_cards(
            battle_id=TEST_BATTLE_ID,
            side="A",
            player_name="测试A",
            cards=[{"id": "B01", "name": "劈斩", "category": "进攻", "aspect": "刃"}],
        )
        print(f"  ✓ sync_available_cards (no-op) OK")

        # ── 清理 ──
        await _cleanup(pool)
        print(f"\n  全部 PostgresSync 测试通过 ✓")

    finally:
        await pool.close()


async def test_disabled_when_no_pool():
    """测试无 DATABASE_URL 时 gracefully disabled"""
    sync = PostgresSync(pool=None)
    assert sync.enabled is False

    # 所有方法应 no-op 不抛异常
    await sync.sync_battle_init("x", "a", "b", {}, {})
    await sync.sync_battle_started("x")
    await sync.sync_submission_made("x", "A", "p", "c1")
    await sync.sync_round_result("x", 1, "c1", "c2", "desc", 0, 0, 20, 20, [], None, False)
    await sync.sync_deck_confirmed("x", "A", ["c1"])
    result = await sync.check_both_decks_confirmed("x")
    assert result is True  # enabled=False 默认返回 True
    await sync.sync_available_cards("x", "A", "p", [])
    print("✓ disabled mode 测试通过（所有方法 no-op）")


async def main():
    print("=" * 60)
    print("Phase 5.1 PostgreSQL 验证测试")
    print("=" * 60)

    try:
        await test_connection()
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        print("  跳过依赖数据库的测试。")
        print("  设置 TEST_DATABASE_URL 或确保本地 PostgreSQL 运行。")
        await test_disabled_when_no_pool()
        return

    try:
        await test_migration()
        await test_postgres_sync()
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    await test_disabled_when_no_pool()

    print("\n" + "=" * 60)
    print("所有测试通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
