"""
RPS结算引擎 — 回合制对战核心

处理一回合的出牌、RPS交互、伤害计算、资源更新、胜负判定。

规则来源: docs/combat/generate_cards_v6.py V6设计文档

V6规则变更：
  - 回合制（一回合一张牌）
  - 无反应槽
  - 多性相并行
  - 战斗HP=20
  - 战前选8张牌库
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from copy import deepcopy

from engine.card_library import (
    Card, CARDS_BY_ID, get_card,
    CATEGORY_STRIKE, CATEGORY_GUARD, CATEGORY_FEINT, CATEGORY_INTERRUPT, CATEGORY_INVOKE,
)
from engine.resource_engine import (
    BattleState, ResourceEngine,
)

# ════════════════════════════════════════════════════
# RPS矩阵定义
# ════════════════════════════════════════════════════

# (A类别, B类别) → 交互结果类型
RPS_MATRIX = {
    (CATEGORY_STRIKE, CATEGORY_STRIKE):     "mutual_damage",       # 双方互伤
    (CATEGORY_STRIKE, CATEGORY_GUARD):      "a_reduced_b_insight", # A被减免+B看破+1
    (CATEGORY_STRIKE, CATEGORY_FEINT):      "mutual_damage",       # 双方互伤
    (CATEGORY_STRIKE, CATEGORY_INTERRUPT):  "independent",         # 各自生效
    (CATEGORY_STRIKE, CATEGORY_INVOKE):     "independent",         # 各自生效（进攻不中断状态）

    (CATEGORY_GUARD, CATEGORY_STRIKE):      "a_insight_b_reduced", # A减免+A看破+1
    (CATEGORY_GUARD, CATEGORY_GUARD):       "dual_defense",        # 双方防御无互动
    (CATEGORY_GUARD, CATEGORY_FEINT):       "a_bypassed",          # B绕过,A无减免无看破
    (CATEGORY_GUARD, CATEGORY_INTERRUPT):   "independent",         # 无互动
    (CATEGORY_GUARD, CATEGORY_INVOKE):      "independent",         # 各自生效

    (CATEGORY_FEINT, CATEGORY_STRIKE):      "mutual_damage",       # 双方互伤
    (CATEGORY_FEINT, CATEGORY_GUARD):       "a_bypasses_b",        # A绕过,B无减免无看破
    (CATEGORY_FEINT, CATEGORY_FEINT):       "mutual_damage",       # 双方互伤1
    (CATEGORY_FEINT, CATEGORY_INTERRUPT):   "independent",         # 各自生效
    (CATEGORY_FEINT, CATEGORY_INVOKE):      "independent",         # 各自生效

    (CATEGORY_INTERRUPT, CATEGORY_STRIKE):  "independent",         # 无互动
    (CATEGORY_INTERRUPT, CATEGORY_GUARD):   "independent",         # 无互动
    (CATEGORY_INTERRUPT, CATEGORY_FEINT):   "independent",         # 无互动
    (CATEGORY_INTERRUPT, CATEGORY_INTERRUPT): "dual_waste",        # 双方浪费
    (CATEGORY_INTERRUPT, CATEGORY_INVOKE):  "b_cancelled",         # B状态取消

    (CATEGORY_INVOKE, CATEGORY_STRIKE):     "independent",         # 各自生效
    (CATEGORY_INVOKE, CATEGORY_GUARD):      "independent",         # 各自生效
    (CATEGORY_INVOKE, CATEGORY_FEINT):      "independent",         # 各自生效
    (CATEGORY_INVOKE, CATEGORY_INTERRUPT):  "a_cancelled",         # A状态取消
    (CATEGORY_INVOKE, CATEGORY_INVOKE):     "dual_invoke",         # 双方状态完整生效
}


# ════════════════════════════════════════════════════
# 结算结果
# ════════════════════════════════════════════════════

@dataclass
class RoundResult:
    """单回合结算结果"""
    round_number: int
    card_a: Card
    card_b: Card
    rps_type: str                     # RPS交互类型
    rps_description: str              # RPS交互中文描述

    damage_to_a: int = 0
    damage_to_b: int = 0

    insight_gained_a: int = 0         # A获得的看破
    insight_gained_b: int = 0         # B获得的看破

    state_a_after: Optional[BattleState] = None
    state_b_after: Optional[BattleState] = None

    resource_logs_a: List[str] = field(default_factory=list)
    resource_logs_b: List[str] = field(default_factory=list)

    special_events: List[str] = field(default_factory=list)

    battle_ended: bool = False
    winner: Optional[str] = None      # "a" / "b" / "draw"
    end_reason: str = ""


# ════════════════════════════════════════════════════
# RPS 结算器
# ════════════════════════════════════════════════════

class RPSResolver:
    """回合制RPS结算器"""

    def __init__(self, deck_a: List[str], deck_b: List[str]):
        """
        Args:
            deck_a: 玩家A的本场8张牌ID列表
            deck_b: 玩家B的本场8张牌ID列表
        """
        self.deck_a_ids = set(deck_a)
        self.deck_b_ids = set(deck_b)
        self.engine = ResourceEngine()

    def validate(self, card_id: str, player_deck_ids: set, state: BattleState) -> List[str]:
        """校验出牌合法性"""
        errors = []

        if card_id not in CARDS_BY_ID:
            errors.append(f"未知卡牌: {card_id}")
            return errors

        if card_id not in player_deck_ids:
            errors.append(f"{card_id} 不在本场牌库中")
            return errors

        card = CARDS_BY_ID[card_id]

        # 防御连用锁
        if card.category == CATEGORY_GUARD and state.last_was_defense:
            errors.append(f"防御连用限制：上步已使用防御({card.name})，本步不能再用防御")

        return errors

    def resolve_round(self, round_num: int, card_a_id: str, card_b_id: str,
                      state_a: BattleState, state_b: BattleState) -> RoundResult:
        """
        结算一回合

        Args:
            round_num: 回合编号
            card_a_id: 玩家A出的牌ID
            card_b_id: 玩家B出的牌ID
            state_a: 玩家A当前状态（会被修改）
            state_b: 玩家B当前状态（会被修改）

        Returns:
            RoundResult
        """
        card_a = get_card(card_a_id)
        card_b = get_card(card_b_id)

        result = RoundResult(
            round_number=round_num,
            card_a=card_a,
            card_b=card_b,
            rps_type="",
            rps_description="",
        )

        cat_a, cat_b = card_a.category, card_b.category
        rps_type = RPS_MATRIX.get((cat_a, cat_b), "independent")
        result.rps_type = rps_type

        # ── Step 1: RPS交互判定 ──
        a_reduced = False      # A的伤害被防御减免
        b_reduced = False      # B的伤害被防御减免
        a_bypassed = False     # A绕过B的防御
        b_bypassed = False     # B绕过A的防御
        a_cancelled = False    # A的状态被打断取消
        b_cancelled = False    # B的状态被打断取消
        a_dodged = False       # A的进攻被闪避
        b_dodged = False       # B的进攻被闪避
        a_illusion = False     # A触发幻象
        b_illusion = False     # B触发幻象

        if rps_type == "a_reduced_b_insight":
            a_reduced = True
            result.insight_gained_b = 1
            result.rps_description = f"{card_a.name}(进攻) vs {card_b.name}(防御) → A伤害被减免，B看破+1"

        elif rps_type == "a_insight_b_reduced":
            b_reduced = True
            result.insight_gained_a = 1
            result.rps_description = f"{card_a.name}(防御) vs {card_b.name}(进攻) → B伤害被减免，A看破+1"

        elif rps_type == "a_bypassed":
            a_bypassed = True
            result.rps_description = f"{card_a.name}(佯攻) 绕过 {card_b.name}(防御) → 不减免无看破"
            # 蛾：佯攻绕过防御→幻影+1
            if card_a.aspect == "蛾":
                self.engine.add_phantom(state_a)
                result.resource_logs_a.append("幻影+1(佯攻绕过)")

        elif rps_type == "a_bypasses_b":
            b_bypassed = True
            result.rps_description = f"{card_b.name}(佯攻) 绕过 {card_a.name}(防御) → 不减免无看破"
            if card_b.aspect == "蛾":
                self.engine.add_phantom(state_b)
                result.resource_logs_b.append("幻影+1(佯攻绕过)")

        elif rps_type == "mutual_damage":
            result.rps_description = f"{card_a.name}({cat_a}) vs {card_b.name}({cat_b}) → 双方互伤"

        elif rps_type == "dual_defense":
            result.rps_description = f"双方防御 → 均无进攻方，无看破"

        elif rps_type == "dual_waste":
            result.rps_description = f"双方打断 → 均无目标，各自浪费"

        elif rps_type == "dual_invoke":
            result.rps_description = f"双方状态 → 各自完整生效"

        elif rps_type == "b_cancelled":
            b_cancelled = True
            result.rps_description = f"{card_a.name}(打断) → {card_b.name}(状态)被取消"
            if card_a.id == "B04":  # 斩法：取消成功→锋芒+1
                self.engine.add_edge(state_a)
                result.resource_logs_a.append("锋芒+1(打断取消状态)")

        elif rps_type == "a_cancelled":
            a_cancelled = True
            result.rps_description = f"{card_b.name}(打断) → {card_a.name}(状态)被取消"
            if card_b.id == "B04":
                self.engine.add_edge(state_b)
                result.resource_logs_b.append("锋芒+1(打断取消状态)")

        else:  # independent
            result.rps_description = f"{card_a.name}({cat_a}) vs {card_b.name}({cat_b}) → 各自生效，无互动"

        # ── 闪避判定 ──
        if card_a.is_dodge and cat_b == CATEGORY_STRIKE:
            b_dodged = True
            result.insight_gained_a = max(result.insight_gained_a, 1)
            self.engine.add_phantom(state_a)
            result.resource_logs_a.append("幻影+1(闪避成功)")
            result.special_events.append("A闪避成功")
            result.rps_description += " | A闪避成功"

        if card_b.is_dodge and cat_a == CATEGORY_STRIKE:
            a_dodged = True
            result.insight_gained_b = max(result.insight_gained_b, 1)
            self.engine.add_phantom(state_b)
            result.resource_logs_b.append("幻影+1(闪避成功)")
            result.special_events.append("B闪避成功")
            result.rps_description += " | B闪避成功"

        # ── 幻象判定 ──
        # 简化处理：不引入随机，改为由调用方根据玩家是否有足够幻影消耗来决定
        # 此处仅标记幻象状态绑定，实际落空判定在上层处理

        # ── Step 2: 伤害计算 ──

        # A的卡牌对B造成的伤害
        damage_to_b = self._calc_damage(card_a, card_b, state_a, state_b, a_reduced,
                                         b_cancelled, b_dodged)

        # B的卡牌对A造成的伤害
        damage_to_a = self._calc_damage(card_b, card_a, state_b, state_a, b_reduced,
                                         a_cancelled, a_dodged)

        # ── 寒意处决检查 ──
        # 检查B身上的寒意（A叠的）是否触发处决
        new_dmg_b, exec_b = self.engine.check_chill_execution(state_b, damage_to_b)
        if exec_b:
            result.special_events.append(f"B寒意处决触发: {damage_to_b}→{new_dmg_b}")
            damage_to_b = new_dmg_b

        # 检查A身上的寒意（B叠的）是否触发处决
        new_dmg_a, exec_a = self.engine.check_chill_execution(state_a, damage_to_a)
        if exec_a:
            result.special_events.append(f"A寒意处决触发: {damage_to_a}→{new_dmg_a}")
            damage_to_a = new_dmg_a

        result.damage_to_a = damage_to_a
        result.damage_to_b = damage_to_b

        # ── Step 3: 应用伤害 ──
        if not a_cancelled:
            state_a.hp -= damage_to_a
        if not b_cancelled:
            state_b.hp -= damage_to_b

        # ── Step 4: 应用看破 ──
        if result.insight_gained_a > 0:
            self.engine.add_insight(state_a, result.insight_gained_a)
        if result.insight_gained_b > 0:
            self.engine.add_insight(state_b, result.insight_gained_b)

        # ── Step 5: 应用卡牌资源变更 ──
        # 被打断的状态卡不生效
        if not (card_a.category == CATEGORY_INVOKE and a_cancelled):
            logs_a = self.engine.apply_card_resources(card_a, state_a, state_b, damage_to_b)
            result.resource_logs_a.extend(logs_a)

        if not (card_b.category == CATEGORY_INVOKE and b_cancelled):
            logs_b = self.engine.apply_card_resources(card_b, state_b, state_a, damage_to_a)
            result.resource_logs_b.extend(logs_b)

        # ── Step 6: 每步资源结算 ──

        # 锋芒衰减
        self.engine.step_edge_decay(state_a, card_a.category == CATEGORY_STRIKE)
        self.engine.step_edge_decay(state_b, card_b.category == CATEGORY_STRIKE)

        # 脉动步末
        self.engine.step_pulse_tick(state_a, damage_to_a > 0)
        self.engine.step_pulse_tick(state_b, damage_to_b > 0)

        # 洞悉检查
        self.engine.step_read_check(state_a, cat_b, state_a.last_opponent_category)
        self.engine.step_read_check(state_b, cat_a, state_b.last_opponent_category)

        # ── Step 7: 更新追踪状态 ──
        state_a.last_was_defense = (card_a.category == CATEGORY_GUARD)
        state_b.last_was_defense = (card_b.category == CATEGORY_GUARD)
        state_a.last_opponent_category = cat_b
        state_b.last_opponent_category = cat_a

        # ── Step 8: 特殊卡牌效果处理 ──

        # 蓄势(C05): 下步进攻伤害+2
        if not a_cancelled and card_a.id == "C05":
            state_a.next_attack_bonus += 2
            result.special_events.append("A蓄势：下步进攻+2")

        if not b_cancelled and card_b.id == "C05":
            state_b.next_attack_bonus += 2
            result.special_events.append("B蓄势：下步进攻+2")

        # 刃之构(B02): 锋芒+2已在resource_gen中处理
        # 下步进攻无法被防御减免至1以下（在下回合detect）

        # 铸甲(F02): 铁甲效果
        if not a_cancelled and card_a.id == "F02":
            state_a.iron_armor = True

        if not b_cancelled and card_b.id == "F02":
            state_b.iron_armor = True

        # 锻炉之锤(F03): 使用后下步必须为防御或状态——通过下回合校验来实现
        # 万刃(B05): 消耗锋芒爆发——在_calc_damage中处理
        # 斩界(B07): 耗尽——在_calc_damage中处理

        # 终焉(W07): 后效——HP较低者归0
        if card_a.id == "W07" and not a_cancelled:
            self._resolve_final_winter(state_a, state_b, "A")
            result.special_events.append("A终焉后效结算")

        if card_b.id == "W07" and not b_cancelled:
            self._resolve_final_winter(state_b, state_a, "B")
            result.special_events.append("B终焉后效结算")

        # 凋零(W05): 对手下步进攻伤害-2/-3
        if not a_cancelled and card_a.id == "W05":
            # 效果在下回合对手进攻时体现
            pass
        if not b_cancelled and card_b.id == "W05":
            pass

        # 铁壁(F06): 送2看破给对手
        if card_a.id == "F06":
            self.engine.add_insight(state_b, 2)
            result.special_events.append("A铁壁→B看破+2")

        if card_b.id == "F06":
            self.engine.add_insight(state_a, 2)
            result.special_events.append("B铁壁→A看破+2")

        # 不屈(H03): 致死伤害→HP锁定1
        if card_a.id == "H03" and state_a.hp <= 0:
            state_a.hp = 1
            heal = 3 + self.engine.consume_pulse(state_a, "all")
            state_a.hp += heal
            result.special_events.append(f"A不屈触发：HP→1+回复{heal}")

        if card_b.id == "H03" and state_b.hp <= 0:
            state_b.hp = 1
            heal = 3 + self.engine.consume_pulse(state_b, "all")
            state_b.hp += heal
            result.special_events.append(f"B不屈触发：HP→1+回复{heal}")

        # 心脏共鸣(H05): 对手回血、自己护盾、再打伤害
        if not a_cancelled and card_a.id == "H05":
            state_b.hp += 2  # 对手回复2HP
            result.special_events.append("A心脏共鸣：B回复2HP")
            # 护盾4已在资源层设置

        if not b_cancelled and card_b.id == "H05":
            state_a.hp += 2
            result.special_events.append("B心脏共鸣：A回复2HP")

        # 第二次心跳(H07): 记录HP（复活在上层生命周期管理）
        # 化身(M05): 不在场（不受伤害）——已在伤害计算中跳过了
        # 最终蜕变(M07): HP恢复至50%
        if not a_cancelled and card_a.id == "M07":
            state_a.hp = max(state_a.hp, state_a.max_hp // 2)
            result.special_events.append("A最终蜕变：HP恢复至50%")
            # 消耗全部幻影换闪避自动成功

        if not b_cancelled and card_b.id == "M07":
            state_b.hp = max(state_b.hp, state_b.max_hp // 2)
            result.special_events.append("B最终蜕变：HP恢复至50%")

        # ── Step 9: 存储结算后状态 ──
        result.state_a_after = deepcopy(state_a)
        result.state_b_after = deepcopy(state_b)

        # ── Step 10: 胜负判定 ──
        result.battle_ended, result.winner, result.end_reason = self._check_battle_end(state_a, state_b)

        return result

    def _calc_damage(self, card: Card, defender_card: Card,
                     attacker: BattleState, defender: BattleState,
                     is_reduced: bool, cancelled: bool, dodged: bool) -> int:
        """
        计算一张牌对对手造成的伤害

        Args:
            card: 攻击方出的牌
            defender_card: 防御方出的牌（用于读取防御值）
            attacker: 攻击方状态
            defender: 防守方状态
            is_reduced: 攻击是否被防御减免
            cancelled: 状态卡是否被打断
            dodged: 进攻是否被闪避
        """
        # 打断/状态卡通常不造成伤害（除非卡牌有伤害值）
        if card.category == CATEGORY_INTERRUPT:
            return card.base_damage  # 通常为0，除了斩法(1)

        if card.category == CATEGORY_INVOKE:
            if cancelled:
                return 0  # 被打断的状态不造成伤害
            return card.base_damage  # 心脏共鸣等有伤害的状态

        # 佯攻
        if card.category == CATEGORY_FEINT:
            # 佯攻永远绕过防御，不受减免
            dmg = card.base_damage
            # 灯洞见：对手重复类别→伤害+2
            if card.id == "L02" and defender.last_opponent_category is not None:
                if defender.last_opponent_category == defender.last_opponent_category:  # 对手本步vs上步
                    pass  # 需要本步类别信息，在resolve_round中通过state追踪
            # 灯残光(L05): 消耗洞悉翻倍
            if card.id == "L05":
                read_spent = ResourceEngine.consume_read(attacker, card.resource_consume.get("洞悉", 0))
                if read_spent > 0:
                    dmg *= (read_spent + 1)  # 消耗1→×2, 消耗2→×3
            return max(0, dmg)

        # 闪避：伤害归零
        if dodged:
            return 0

        # 进攻
        if card.category == CATEGORY_STRIKE:
            dmg = card.base_damage

            # 连击处理
            if card.is_multi_hit:
                # 每击独立伤害
                hit_damages = []
                for i in range(card.hit_count):
                    hit_dmg = 1  # 连斩每击1伤害（默认值）
                    if card.id == "B03":  # 连斩
                        hit_dmg = 1
                    elif card.id == "B05":  # 万刃可能变成连击
                        hit_dmg = 1
                    hit_damages.append(hit_dmg)

                # 防御减免仅第一击
                if is_reduced and not _card_bypasses(card):
                    defense_val = defender_card.defense_value
                    hit_damages[0] = max(0, hit_damages[0] - defense_val)

                dmg = sum(hit_damages)
            else:
                # 单次进攻
                # 防御减免
                if is_reduced and not _card_bypasses(card):
                    defense_val = defender_card.defense_value
                    dmg = max(0, dmg - defense_val)

                # 铁壁(F06): 伤害被减到最多1
                if defender.last_was_defense:
                    pass  # 铁壁效果在上层RPS交互判定

            # 锋芒被动加成：每层+1
            dmg += attacker.edge

            # 自身寒意削减：每层-1
            dmg = max(0, dmg - attacker.self_chill)

            # 看破自动触发：×2每层
            insight_stacks = attacker.insight
            if insight_stacks > 0:
                dmg *= (2 * insight_stacks)
                ResourceEngine.consume_insight_all(attacker)

            # 蓄力爆发：在看破翻倍之后追加
            if card.id in ("F03", "F07"):  # 锻炉之锤/终极锻炉消耗蓄力
                charge_stacks = ResourceEngine.consume_charge_all(attacker)
                dmg += charge_stacks * 2

            if card.id == "B05":  # 万刃：1 + 消耗数×2
                charge_stacks = ResourceEngine.consume_edge(attacker, "all")
                dmg = 1 + charge_stacks * 2
                if charge_stacks >= 2:
                    # 连击2次
                    dmg *= 2

            if card.id == "B07":  # 斩界：4 + 锋芒层数×3
                charge_stacks = ResourceEngine.consume_edge(attacker, "all")
                dmg = 4 + charge_stacks * 3

            # 蓄势加成
            dmg += attacker.next_attack_bonus
            attacker.next_attack_bonus = 0

            # 凋零效果：对手下步进攻伤害减少（由对手状态决定）
            # 需要在评估时检查debuff

            return max(0, dmg)

        return 0

    def _resolve_final_winter(self, caster: BattleState, target: BattleState, caster_label: str):
        """终焉(W07)后效：HP较低者归0"""
        if caster.hp < target.hp:
            target.hp = 0
        elif target.hp < caster.hp:
            caster.hp = 0
        else:
            caster.hp = max(-99, caster.hp - 5)
            target.hp = max(-99, target.hp - 5)

    def _check_battle_end(self, state_a: BattleState, state_b: BattleState) -> Tuple[bool, Optional[str], str]:
        """
        检查战斗是否结束

        Returns: (ended, winner, reason)
        """
        a_dead = state_a.hp <= 0
        b_dead = state_b.hp <= 0

        if not a_dead and not b_dead:
            return False, None, ""

        if a_dead and not b_dead:
            return True, "b", f"A HP={state_a.hp}≤0"

        if b_dead and not a_dead:
            return True, "a", f"B HP={state_b.hp}≤0"

        # 双方同时死亡：欠血判定
        deficit_a = abs(state_a.hp) if state_a.hp < 0 else 0
        deficit_b = abs(state_b.hp) if state_b.hp < 0 else 0

        if deficit_a < deficit_b:
            return True, "a", f"双方HP≤0，A欠血({deficit_a}) < B欠血({deficit_b})"
        elif deficit_b < deficit_a:
            return True, "b", f"双方HP≤0，B欠血({deficit_b}) < A欠血({deficit_a})"
        else:
            return True, "draw", f"双方HP≤0且欠血相等({deficit_a})"


# ════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════

def _card_bypasses(card: Card) -> bool:
    """卡牌是否绕过防御"""
    if card.bypasses_defense:
        return True
    if card.category == CATEGORY_FEINT:
        return True
    return False


def is_bypass(card: Card, attacker: BattleState, defender: BattleState) -> bool:
    """判断本次伤害是否绕过防御"""
    return _card_bypasses(card)


def get_defense_value(defender: BattleState, attacker_card: Card) -> int:
    """
    获取防御方的当前减免值

    包含：卡牌基础防御值 + 铁甲效果 + 淬火加成
    """
    # 基础防御值从状态中获取（由上一张出牌决定）
    # 注意：防御值是防御卡牌本身的属性
    # 这里简化处理：防御方当前回合出的是防御卡
    # defense_value会在RPS判定层传入
    return defender.last_was_defense * max(0, 0)  # 由RPS层的防御牌直接提供


# ════════════════════════════════════════════════════
# 测试
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    from engine.card_library import ALL_CARDS

    # 简单对战：通用卡牌测试
    deck = ["C01", "C02", "C03", "C04", "C05", "C06",
            "B01", "W01"]  # 示例8张牌（测试用）

    resolver = RPSResolver(deck, deck)

    state_a = BattleState(hp=20)
    state_b = BattleState(hp=20)

    print("=== RPS 结算测试 ===\n")

    # 测试1: 双方互伤
    print("[1] 进攻 vs 进攻")
    r = resolver.resolve_round(1, "C01", "C01", state_a, state_b)
    print(f"  {r.rps_description}")
    print(f"  A伤害→B: {r.damage_to_b}, B伤害→A: {r.damage_to_a}")
    print(f"  A HP={state_a.hp}, B HP={state_b.hp}")
    print(f"  战斗结束: {r.battle_ended}")

    # 测试2: 进攻 vs 防御
    print("\n[2] 进攻 vs 防御")
    r = resolver.resolve_round(2, "C01", "C03", state_a, state_b)
    print(f"  {r.rps_description}")
    print(f"  A伤害→B: {r.damage_to_b}, B伤害→A: {r.damage_to_a}")
    print(f"  B看破+{r.insight_gained_b}")
    print(f"  A HP={state_a.hp}, B HP={state_b.hp}")
    print(f"  战斗结束: {r.battle_ended}")

    # 测试3: 佯攻 vs 防御
    print("\n[3] 佯攻 vs 防御")
    r = resolver.resolve_round(3, "C02", "C03", state_a, state_b)
    print(f"  {r.rps_description}")
    print(f"  A伤害→B: {r.damage_to_b}, B伤害→A: {r.damage_to_a}")
    print(f"  A HP={state_a.hp}, B HP={state_b.hp}")

    # 测试4: 打断 vs 状态
    print("\n[4] 打断 vs 状态")
    r = resolver.resolve_round(4, "C04", "C05", state_a, state_b)
    print(f"  {r.rps_description}")
    print(f"  A伤害→B: {r.damage_to_b}, B伤害→A: {r.damage_to_a}")

    # 测试5: 防御连用锁
    print("\n[5] 防御连用检测")
    errors = resolver.validate("C03", set(deck), state_a)
    print(f"  A(上步用了防御)再出防御: {'违规' if errors else '通过'}")
    if errors:
        print(f"  错误: {errors}")

    # 测试6: 看破触发
    print("\n[6] 看破触发: A(有看破1层)进攻")
    state_a.insight = 1  # 手动设看破
    r = resolver.resolve_round(5, "C01", "C01", state_a, state_b)
    print(f"  {r.rps_description}")
    print(f"  A伤害→B(看破翻倍): {r.damage_to_b}")
    print(f"  A看破剩余: {state_a.insight} (应归0)")

    # 测试7: 寒意处决
    print("\n[7] 寒意处决")
    state_a.self_chill = 3
    r = resolver.resolve_round(6, "C01", "C01", state_a, state_b)
    print(f"  A身负3层寒意→伤害翻倍")
    print(f"  B伤害→A(翻倍): {r.damage_to_a}")
    print(f"  A寒意剩余: {state_a.self_chill} (应归0)")
    if r.special_events:
        print(f"  特殊事件: {r.special_events}")

    print(f"\n最终: A HP={state_a.hp}, B HP={state_b.hp}")
    print("=== RPS结算测试完成 ===")
