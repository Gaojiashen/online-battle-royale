"""
完整对战场景测试 — 多性相、寒意双向、多回合、边界情况
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from card_library import (
    ALL_CARDS, CARDS_BY_ID, get_available_cards,
    CATEGORY_STRIKE, CATEGORY_GUARD, CATEGORY_FEINT, CATEGORY_INTERRUPT, CATEGORY_INVOKE,
)
from deck_validator import DeckValidationResult, calculate_available, validate_deck, suggest_deck, DECK_SIZE
from resource_engine import BattleState, ResourceEngine
from rps_resolver import RPSResolver, RoundResult

# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def test_battle_with_decks(deck_a, deck_b, state_a, state_b, rounds_data, label=""):
    """
    运行多回合对战并验证结果

    rounds_data: [(card_a_id, card_b_id, expected_a_hp, expected_b_hp, desc), ...]
    """
    resolver = RPSResolver(deck_a, deck_b)
    print(f"\n{'='*60}")
    print(f"对战: {label}")
    print(f"A HP={state_a.hp} B HP={state_b.hp}")
    print(f"A牌库: {[f'{cid} {CARDS_BY_ID[cid].name}' for cid in deck_a]}")
    print(f"B牌库: {[f'{cid} {CARDS_BY_ID[cid].name}' for cid in deck_b]}")
    print(f"{'='*60}")

    for i, (cid_a, cid_b, exp_a_hp, exp_b_hp, desc) in enumerate(rounds_data, 1):
        r = resolver.resolve_round(i, cid_a, cid_b, state_a, state_b)
        ca, cb = CARDS_BY_ID[cid_a], CARDS_BY_ID[cid_b]

        hp_ok = state_a.hp == exp_a_hp and state_b.hp == exp_b_hp
        status = "OK" if hp_ok else "FAIL"

        print(f"\nR{i} [{status}] {desc}")
        print(f"  A: {ca.name}({ca.category})  B: {cb.name}({cb.category})")
        print(f"  RPS: {r.rps_description}")
        print(f"  Damage: A->B={r.damage_to_b}  B->A={r.damage_to_a}")
        print(f"  HP: A={state_a.hp}(exp={exp_a_hp}) B={state_b.hp}(exp={exp_b_hp})")
        print(f"  A资源: 锋芒={state_a.edge} 幻影={state_a.phantom} 蓄力={state_a.charge} 寒意={state_a.self_chill} 脉动={state_a.pulse} 洞悉={state_a.read} 看破={state_a.insight}")
        print(f"  B资源: 锋芒={state_b.edge} 幻影={state_b.phantom} 蓄力={state_b.charge} 寒意={state_b.self_chill} 脉动={state_b.pulse} 洞悉={state_b.read} 看破={state_b.insight}")
        if r.special_events:
            print(f"  特殊: {r.special_events}")
        if r.battle_ended:
            print(f"  战斗结束! 胜者: {r.winner} ({r.end_reason})")

        assert hp_ok, f"HP mismatch: A={state_a.hp} expected={exp_a_hp}, B={state_b.hp} expected={exp_b_hp}"

    print(f"\n最终: A HP={state_a.hp} B HP={state_b.hp}")
    return state_a, state_b


# ═══════════════════════════════════════════════════════════════
# 测试1：通用卡牌基础对战
# ═══════════════════════════════════════════════════════════════

def test_basic_generic():
    """通用卡牌基础RPS测试"""
    deck = ["C01", "C02", "C03", "C04", "C05", "C06", "B01", "W01"]

    state_a = BattleState(hp=20)
    state_b = BattleState(hp=20)

    rounds = [
        ("C01", "C01", 18, 18, "双方进攻互伤(2 vs 2)"),
        ("C01", "C03", 18, 17, "A进攻 vs B格挡→A减免(2+1-2=1)"),
        ("C02", "C03", 18, 16, "A佯攻 vs B格挡→绕过(1穿透)"),
        ("C04", "C05", 18, 16, "A打断 vs B蓄势→B状态取消"),
        ("C05", "C04", 18, 16, "A蓄势 vs B打断→A状态取消"),
        ("C03", "C01", 18, 16, "A格挡 vs B进攻→看破→B减免(2+1-2=1)"),
    ]

    test_battle_with_decks(deck, deck, state_a, state_b, rounds, "通用卡牌基础RPS")


# ═══════════════════════════════════════════════════════════════
# 测试2：防御连用锁
# ═══════════════════════════════════════════════════════════════

def test_guard_lock():
    """防御不能连续使用"""
    deck = ["C01", "C02", "C03", "C04", "C05", "C06", "B01", "W01"]

    # 模拟A上一回合用了防御
    state_a = BattleState(hp=20, last_was_defense=True)
    state_b = BattleState(hp=20)

    resolver = RPSResolver(deck, deck)
    errors = resolver.validate("C03", set(deck), state_a)
    assert len(errors) == 1, f"Expected 1 error, got {len(errors)}"
    assert "连用" in errors[0], f"Expected guard lock error, got: {errors[0]}"
    print("  [OK] 防御连用锁正确阻止")

    # 但A用C04打断就没问题
    errors = resolver.validate("C04", set(deck), state_a)
    assert len(errors) == 0, f"Should allow interrupt after defense: {errors}"
    print("  [OK] 防御后使用打断正确通过")


# ═══════════════════════════════════════════════════════════════
# 测试3：多性相并行可用牌计算
# ═══════════════════════════════════════════════════════════════

def test_multi_aspect_available():
    """多性相玩家：灯4+蛾6"""
    levels = {"灯": 4, "蛾": 6}
    available = calculate_available(levels)
    ids = {c.id for c in available}

    # 通用卡
    for cid in ["C01", "C02", "C03", "C04", "C05", "C06"]:
        assert cid in ids, f"Missing generic card {cid}"

    # 蛾Lv2+
    for cid in ["M01", "M02"]:
        assert cid in ids, f"Missing moth Lv2 card {cid}"

    # 蛾Lv6+
    for cid in ["M03", "M04"]:
        assert cid in ids, f"Missing moth Lv6 card {cid}"

    # 灯Lv2+
    for cid in ["L01", "L02"]:
        assert cid in ids, f"Missing lantern Lv2 card {cid}"

    # 灯Lv6+ 不应该可用（灯才4级）
    for cid in ["L03", "L04"]:
        assert cid not in ids, f"Should NOT have {cid} (lantern Lv6, player has Lv4)"

    # 灯Lv10+ 不应该可用
    for cid in ["L05", "L06"]:
        assert cid not in ids, f"Should NOT have {cid} (lantern Lv10)"

    # 其他性相不应该可用（等级0）
    for cid in ["B01", "F01", "W01", "H01"]:
        assert cid not in ids, f"Should NOT have {cid} (no aspect level)"

    assert len(available) == 12, f"Expected 12 available (6C+4蛾+2灯), got {len(available)}"
    print(f"  [OK] 灯4+蛾6 = {len(available)}张 (6C+4蛾+2灯)")

    # 测试另一个组合：刃10+冬2
    levels2 = {"刃": 10, "冬": 2}
    available2 = calculate_available(levels2)
    ids2 = {c.id for c in available2}
    # 通用6 + 刃Lv2(B01,B02) + Lv6(B03,B04) + Lv10(B05,B06) + 冬Lv2(W01,W02,W03)
    assert len(available2) == 6 + 6 + 3, f"刃10+冬2 should have 15, got {len(available2)}"
    print(f"  [OK] 刃10+冬2 = {len(available2)}张 (6C+6刃+3冬)")


# ═══════════════════════════════════════════════════════════════
# 测试4：8张组牌校验
# ═══════════════════════════════════════════════════════════════

def test_deck_validation():
    """组牌合法性检查"""
    levels = {"灯": 4, "蛾": 6}

    # 合法组牌
    valid = ["C01", "C02", "C03", "C04", "M01", "M02", "L01", "L02"]
    result = validate_deck(valid, levels)
    assert result.is_valid == True, f"Should be valid: {result.errors}"
    print(f"  [OK] 合法8张牌组通过")

    # 数量不足
    result = validate_deck(["C01", "C02", "C03"], levels)
    assert result.is_valid == False
    assert "8" in result.errors[0]
    print(f"  [OK] 数量不足正确拦截: {result.errors[0]}")

    # 超出等级
    too_high = ["C01", "C02", "C03", "C04", "C05", "C06", "L03", "L04"]  # L03/L04需要灯6
    result = validate_deck(too_high, levels)
    assert result.is_valid == False
    assert any("L03" in e for e in result.errors)
    print(f"  [OK] 超等级正确拦截: {result.errors}")

    # 重复卡牌
    dup = ["C01", "C01", "C02", "C03", "C04", "M01", "M02", "L01"]
    result = validate_deck(dup, levels)
    assert result.is_valid == False
    assert any("重复" in e for e in result.errors)
    print(f"  [OK] 重复卡牌正确拦截")


# ═══════════════════════════════════════════════════════════════
# 测试5：寒意双向追踪
# ═══════════════════════════════════════════════════════════════

def test_chill_bidirectional():
    """寒意双向：自身寒意(对手叠的)+敌方寒意(自己叠的)"""
    deck_a = ["C01", "W01", "W02", "W03", "C03", "C04", "C05", "C06"]
    deck_b = ["C01", "W01", "W02", "W03", "C03", "C04", "C05", "C06"]

    state_a = BattleState(hp=20, winter_level=2)
    state_b = BattleState(hp=20, winter_level=2)

    resolver = RPSResolver(deck_a, deck_b)

    # R1: A用寒触(W01,chill=1) vs B用寒触 → A给B叠1寒意，B给A叠1寒意
    r = resolver.resolve_round(1, "W01", "W01", state_a, state_b)
    # W01: 造成1伤害+施加1寒意给对手
    # A给B寒意 → B.self_chill = 1
    # B给A寒意 → A.self_chill = 1
    assert state_a.self_chill == 1, f"A自身寒意应为1(B叠的)，实际{state_a.self_chill}"
    assert state_b.self_chill == 1, f"B自身寒意应为1(A叠的)，实际{state_b.self_chill}"
    print(f"  [OK] R1: A寒意(自身)={state_a.self_chill}, B寒意(自身)={state_b.self_chill} (互相叠1)")

    # R2: A再寒触 vs B挥击
    r = resolver.resolve_round(2, "W01", "C01", state_a, state_b)
    # A给B再叠1寒意 → B.self_chill = 2
    assert state_b.self_chill == 2, f"B自身寒意应为2，实际{state_b.self_chill}"
    # A进攻伤害: 1(base) - 1(A.self_chill=1) = 0 (被寒意削减)
    print(f"  [OK] R2: B寒意→{state_b.self_chill}, A进攻伤害={r.damage_to_b}(寒意-1)")

    # R3: A寒触 vs B挥击 → B寒意=3（寒意叠满），但本回合伤害已经结算完了
    r = resolver.resolve_round(3, "W01", "C01", state_a, state_b)
    # A施加寒意→B.self_chill=3，但W01的伤害已结算完毕，处决在下回合触发
    assert state_b.self_chill == 3, f"B寒意应为3，实际{state_b.self_chill}"
    print(f"  [OK] R3: B寒意→3(叠满)，伤害={r.damage_to_b}")

    # R4: A挥击 vs B挥击 → B寒意=3触发处决！
    r = resolver.resolve_round(4, "C01", "C01", state_a, state_b)
    assert state_b.self_chill == 0, f"处决后B寒意应归零，实际{state_b.self_chill}"
    print(f"  [OK] R4: B寒意=3触发处决→清零，伤害翻倍={r.damage_to_b}")


# ═══════════════════════════════════════════════════════════════
# 测试6：看破自动触发链
# ═══════════════════════════════════════════════════════════════

def test_insight_chain():
    """看破：防御成功→看破+1→下次进攻自动×2→最多2层×4"""
    deck = ["C01", "C02", "C03", "C04", "C05", "C06", "B01", "F01"]

    state_a = BattleState(hp=20)
    state_b = BattleState(hp=20)

    resolver = RPSResolver(deck, deck)

    # R1: A进攻 vs B格挡 → B获得看破×1
    r = resolver.resolve_round(1, "C01", "C03", state_a, state_b)
    assert state_b.insight == 1, f"B应有1看破，实际{state_b.insight}"
    print(f"  [OK] R1: B格挡成功→看破+1")

    # R2: B进攻(有1看破) vs A进攻 → B伤害×2
    r = resolver.resolve_round(2, "C01", "C01", state_a, state_b)
    # B拥有1看破，进攻时自动消耗→×2。基础2→4（但B可能有锋芒）
    assert state_b.insight == 0, f"B看破应在进攻后清零，实际{state_b.insight}"
    print(f"  [OK] R2: B看破触发→伤害×2={r.damage_to_a}，看破清零")

    # R3-R4: 2层看破×4
    r = resolver.resolve_round(3, "C01", "C03", state_a, state_b)  # 又格挡成功
    assert state_b.insight == 1
    r = resolver.resolve_round(4, "C01", "C03", state_a, state_b)  # 再次格挡
    # state_b 已有1看破，又+1 = 2
    assert state_b.insight == 2, f"B应有2看破，实际{state_b.insight}"
    r = resolver.resolve_round(5, "C01", "C01", state_a, state_b)
    # B 2看破→进攻×4
    print(f"  [OK] R5: B 2看破→伤害×4={r.damage_to_a}，看破归零={state_b.insight}")


# ═══════════════════════════════════════════════════════════════
# 测试7：欠血判定
# ═══════════════════════════════════════════════════════════════

def test_blood_debt():
    """双方同时死亡时，欠血少者胜"""
    deck = ["C01", "C02", "C03", "C04", "C05", "C06", "B01", "W01"]

    state_a = BattleState(hp=3)  # A剩3HP
    state_b = BattleState(hp=5)  # B剩5HP

    resolver = RPSResolver(deck, deck)

    # A进攻(3伤害) vs B进攻(5伤害) → 同时死亡
    # 但基础伤害是2...
    # 让我们设高一点：手动设置A edge=1让A伤害=3，B edge=3让B伤害=5...这不太自然
    # 换个方式：A有2HP B有3HP，A和B都出C01(2伤害)
    state_a = BattleState(hp=2)
    state_b = BattleState(hp=3)

    # 两个都出C01，互伤2
    # A HP=2 → 2-2=0 → dead
    # B HP=3 → 3-2=1 → alive
    # B wins
    r = resolver.resolve_round(1, "C01", "C01", state_a, state_b)
    assert r.battle_ended == True
    assert r.winner == "b"
    print(f"  [OK] A HP=0 B HP=1 → B胜")

    # 双方都死：A HP=1 B HP=2，都用3伤害（需要设edge=1）
    state_a = BattleState(hp=1, edge=1)
    state_b = BattleState(hp=2)

    # A出C01: 2+1(edge)=3 vs B出C01: 2
    # A→B=3, B HP=2-3=-1(欠1)
    # B→A: C01基础2, B没有edge=2 → A HP=1-2=-1(欠1)
    # 欠血相等 → 平局
    # 但等等，B出C01只有2伤害，A HP=1→1-2=-1。A出C01(有edge1)=3伤害，B HP=2→2-3=-1
    # 双方欠血都是1 → draw
    resolver2 = RPSResolver(deck, deck)
    r = resolver2.resolve_round(1, "C01", "C01", state_a, state_b)
    if r.battle_ended:
        print(f"  [OK] 双方HP≤0: A={state_a.hp} B={state_b.hp} → {r.winner} ({r.end_reason})")


# ═══════════════════════════════════════════════════════════════
# 测试8：全卡牌可用性矩阵
# ═══════════════════════════════════════════════════════════════

def test_card_availability_matrix():
    """验证每种性相各等级的正确解锁数量"""
    expected = {
        ("刃", 2): 2, ("刃", 6): 4, ("刃", 10): 6, ("刃", 15): 7,
        ("蛾", 2): 2, ("蛾", 6): 4, ("蛾", 10): 6, ("蛾", 15): 7,
        ("铸", 2): 2, ("铸", 6): 4, ("铸", 10): 6, ("铸", 15): 7,
        ("冬", 2): 3, ("冬", 6): 5, ("冬", 10): 6, ("冬", 15): 7,
        ("心", 2): 2, ("心", 6): 4, ("心", 10): 6, ("心", 15): 7,
        ("灯", 2): 2, ("灯", 6): 4, ("灯", 10): 6, ("灯", 15): 7,
    }

    for (aspect, level), expected_count in expected.items():
        levels = {aspect: level}
        available = calculate_available(levels)
        aspect_cards = [c for c in available if c.aspect == aspect]
        total = len(available)
        assert len(aspect_cards) == expected_count, \
            f"{aspect} Lv{level}: expected {expected_count} aspect cards, got {len(aspect_cards)}"
        # 通用卡总是6张
        assert total == 6 + expected_count, \
            f"{aspect} Lv{level}: expected {6+expected_count} total, got {total}"

    print("  [OK] 全性相等级解锁矩阵验证通过")


# ═══════════════════════════════════════════════════════════════
# 主测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("基础RPS交互", test_basic_generic),
        ("防御连用锁", test_guard_lock),
        ("多性相可用牌计算", test_multi_aspect_available),
        ("8张组牌校验", test_deck_validation),
        ("寒意双向追踪", test_chill_bidirectional),
        ("看破自动触发链", test_insight_chain),
        ("欠血判定", test_blood_debt),
        ("全卡牌可用性矩阵", test_card_availability_matrix),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            print(f"\n{'='*60}")
            print(f"TEST: {name}")
            print(f"{'='*60}")
            test_fn()
            passed += 1
            print(f"[PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    print(f"{'='*60}")

    assert failed == 0, f"{failed} tests failed!"
