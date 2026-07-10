"""
资源流转引擎 — 六性相资源的生成/消耗/衰减规则

V6 六资源：
  锋芒(Edge)    刃 · 自身buff · 上限3 · 进攻造成≥1伤害→+1 | 未进攻→-1
  幻影(Phantom)  蛾 · 自身buff · 上限3 · 闪避/幻象落空/佯攻绕过→+1 | 无衰减
  蓄力(Charge)   铸 · 自身buff · 上限3 · 使用防御→+1 | 进攻时自动消耗全部
  寒意(Chill)    冬 · 敌方debuff · 上限3 · 各类冬牌施加 | 处决后清零
  脉动(Pulse)    心 · 自身buff · 上限4 · 每步+1,状态+1 | 受伤-1
  洞悉(Read)     灯 · 自身buff · 上限2 · 对手重复类别/防御→+1 | 无衰减
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from engine.card_library import (
    Card, CATEGORY_STRIKE, CATEGORY_GUARD, CATEGORY_FEINT,
    CATEGORY_INTERRUPT, CATEGORY_INVOKE
)


# ════════════════════════════════════════════════════
# 玩家战斗状态
# ════════════════════════════════════════════════════

@dataclass
class BattleState:
    """单个玩家的战斗状态"""
    hp: int = 20                      # 战斗HP
    max_hp: int = 20                  # 最大战斗HP

    # 性相等级
    blade_level: int = 0              # 刃
    moth_level: int = 0               # 蛾
    forge_level: int = 0              # 铸
    winter_level: int = 0             # 冬
    heart_level: int = 0              # 心
    lantern_level: int = 0            # 灯

    # 资源
    edge: int = 0                     # 锋芒 0-3
    phantom: int = 0                  # 幻影 0-3
    charge: int = 0                   # 蓄力 0-3
    self_chill: int = 0               # 自身寒意（对手叠的）0-3
    pulse: int = 0                    # 脉动 0-4
    read: int = 0                     # 洞悉 0-2

    # 通用战斗状态
    insight: int = 0                  # 看破层数 0-2
    last_was_defense: bool = False    # 上步使用防御（防御连用锁）
    last_opponent_category: Optional[str] = None  # 上步对手行动类别（洞悉判定）

    # 特殊状态
    iron_armor: bool = False          # 铁甲（铸甲效果）
    next_defense_bonus: int = 0       # 下步防御减免额外加成
    next_attack_bonus: int = 0        # 下步进攻伤害加成（蓄势）
    attack_penalty: int = 0           # 攻击力永久减值（第二次心跳复活后）
    invulnerable: bool = False        # 无敌（化身/终极锻炉）
    dodge_auto_success: int = 0       # 自动闪避成功剩余步数
    damage_halved_step: Optional[int] = None  # 生命链接：减伤步号

    # 持久属性
    game_hp: int = 100                # 游戏HP（持久）

    def get_aspect_levels(self) -> Dict[str, int]:
        """返回所有性相等级字典"""
        return {
            "刃": self.blade_level,
            "蛾": self.moth_level,
            "铸": self.forge_level,
            "冬": self.winter_level,
            "心": self.heart_level,
            "灯": self.lantern_level,
        }

    def get_resource_display(self) -> Dict[str, int]:
        """返回所有资源当前值"""
        return {
            "锋芒": self.edge,
            "幻影": self.phantom,
            "蓄力": self.charge,
            "自身寒意": self.self_chill,
            "脉动": self.pulse,
            "洞悉": self.read,
            "看破": self.insight,
        }


# ════════════════════════════════════════════════════
# 资源操作
# ════════════════════════════════════════════════════

class ResourceEngine:
    """资源流转引擎"""

    # 各资源上限
    CAPS = {
        "锋芒": 3, "幻影": 3, "蓄力": 3,
        "寒意": 3, "脉动": 4, "洞悉": 2, "看破": 2
    }

    @staticmethod
    def add_edge(state: BattleState, amount: int = 1):
        """增加锋芒"""
        state.edge = min(ResourceEngine.CAPS["锋芒"], state.edge + amount)

    @staticmethod
    def add_phantom(state: BattleState, amount: int = 1):
        """增加幻影"""
        state.phantom = min(ResourceEngine.CAPS["幻影"], state.phantom + amount)

    @staticmethod
    def add_charge(state: BattleState, amount: int = 1):
        """增加蓄力"""
        state.charge = min(ResourceEngine.CAPS["蓄力"], state.charge + amount)

    @staticmethod
    def add_chill(state: BattleState, amount: int = 1):
        """对目标施加寒意（增加自身寒意）"""
        state.self_chill = min(ResourceEngine.CAPS["寒意"], state.self_chill + amount)

    @staticmethod
    def add_pulse(state: BattleState, amount: int = 1):
        """增加脉动"""
        state.pulse = min(ResourceEngine.CAPS["脉动"], state.pulse + amount)

    @staticmethod
    def add_read(state: BattleState, amount: int = 1):
        """增加洞悉"""
        state.read = min(ResourceEngine.CAPS["洞悉"], state.read + amount)

    @staticmethod
    def add_insight(state: BattleState, amount: int = 1):
        """增加看破"""
        state.insight = min(ResourceEngine.CAPS["看破"], state.insight + amount)

    @staticmethod
    def consume_edge(state: BattleState, amount: object = "all") -> int:
        """消耗锋芒，返回消耗量"""
        if amount == "all":
            consumed = state.edge
            state.edge = 0
            return consumed
        consumed = min(state.edge, int(amount))
        state.edge -= consumed
        return consumed

    @staticmethod
    def consume_phantom(state: BattleState, amount: int = 1) -> int:
        """消耗幻影，返回消耗量"""
        consumed = min(state.phantom, amount)
        state.phantom -= consumed
        return consumed

    @staticmethod
    def consume_charge_all(state: BattleState) -> int:
        """消耗全部蓄力，返回消耗量"""
        consumed = state.charge
        state.charge = 0
        return consumed

    @staticmethod
    def consume_pulse(state: BattleState, amount: object = 1) -> int:
        """消耗脉动，返回消耗量"""
        if amount == "all":
            consumed = state.pulse
            state.pulse = 0
            return consumed
        consumed = min(state.pulse, int(amount))
        state.pulse -= consumed
        return consumed

    @staticmethod
    def consume_read(state: BattleState, amount: int = 1) -> int:
        """消耗洞悉，返回消耗量"""
        consumed = min(state.read, amount)
        state.read -= consumed
        return consumed

    @staticmethod
    def consume_insight_all(state: BattleState) -> int:
        """消耗全部看破（进攻时自动触发），返回消耗量"""
        consumed = state.insight
        state.insight = 0
        return consumed

    # ── 每步资源结算 ──

    @staticmethod
    def step_edge_decay(state: BattleState, did_attack: bool):
        """锋芒衰减：本步未进攻→-1"""
        if not did_attack and state.edge > 0:
            state.edge -= 1

    @staticmethod
    def step_pulse_tick(state: BattleState, took_damage: bool):
        """脉动步末结算：自动+1；受伤→-1"""
        state.pulse = min(ResourceEngine.CAPS["脉动"], state.pulse + 1)
        if took_damage and state.pulse > 0:
            state.pulse -= 1

    @staticmethod
    def step_read_check(state: BattleState, opponent_category: str, opponent_prev_category: Optional[str]):
        """洞悉检查：对手重复类别→+1；对手使用防御→+1"""
        if opponent_prev_category is not None and opponent_category == opponent_prev_category:
            ResourceEngine.add_read(state)
        if opponent_category == CATEGORY_GUARD:
            ResourceEngine.add_read(state)

    @staticmethod
    def check_chill_execution(state: BattleState, damage: int) -> (int, bool):
        """
        寒意处决检查：若寒意=3且受到伤害→伤害翻倍→寒意清零
        Returns: (modified_damage, did_execute)
        """
        if state.self_chill >= 3 and damage > 0:
            state.self_chill = 0
            return damage * 2, True
        return damage, False

    # ── 卡牌资源生成/消耗 ──

    @staticmethod
    def apply_card_resources(card: Card, player: BattleState, opponent: BattleState, damage_dealt: int):
        """
        根据卡牌效果应用资源变更

        处理卡牌 data 中的 resource_gen 和 resource_consume
        以及各类别固有的资源生成规则
        """
        logs = []

        # === 通用规则：按类别 ===

        # 刃：进攻造成≥1伤害→锋芒+1
        if card.category == CATEGORY_STRIKE and damage_dealt >= 1:
            ResourceEngine.add_edge(player)
            logs.append(f"锋芒+1(进攻命中)")

        # 蛾：佯攻绕过防御→幻影+1（在RPS结算层处理）

        # 铸：使用防御→蓄力+1
        if card.category == CATEGORY_GUARD:
            ResourceEngine.add_charge(player)
            logs.append(f"蓄力+1(使用防御)")

        # 心：使用状态→脉动+1
        if card.category == CATEGORY_INVOKE:
            ResourceEngine.add_pulse(player)
            logs.append(f"脉动+1(使用状态)")

        # === 卡牌特定资源生成 ===
        for res, amount in card.resource_gen.items():
            if res == "锋芒":
                ResourceEngine.add_edge(player, amount)
                logs.append(f"锋芒+{amount}")
            elif res == "幻影":
                ResourceEngine.add_phantom(player, amount)
                logs.append(f"幻影+{amount}")
            elif res == "蓄力":
                ResourceEngine.add_charge(player, amount)
                logs.append(f"蓄力+{amount}")
            elif res == "脉动":
                ResourceEngine.add_pulse(player, amount)
                logs.append(f"脉动+{amount}")

        # === 寒意施加 ===
        if card.applies_chill:
            # W07 终焉：直接设3层（覆盖）
            if card.id == "W07":
                opponent.self_chill = 3
                logs.append(f"对手寒意→3(终焉覆盖)")
            else:
                ResourceEngine.add_chill(opponent, card.chill_amount)
                logs.append(f"对手寒意+{card.chill_amount}")

        # === 卡牌资源消耗（在结算时处理，这里记录） ===
        for res, amount in card.resource_consume.items():
            if amount == "all":
                logs.append(f"消耗全部{res}")
            else:
                logs.append(f"消耗{res}×{amount}")

        return logs


# ════════════════════════════════════════════════════
# 测试
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    from engine.card_library import get_card

    engine = ResourceEngine()

    # 测试资源上限
    state = BattleState()
    engine.add_edge(state, 5)
    assert state.edge == 3, f"锋芒应上限3，实际{state.edge}"
    print("资源上限测试通过")

    # 测试寒意处决
    state.self_chill = 3
    dmg, did_exec = engine.check_chill_execution(state, 5)
    assert did_exec == True
    assert dmg == 10
    assert state.self_chill == 0
    print("寒意处决测试通过")

    # 测试脉动步末
    state2 = BattleState(pulse=2)
    engine.step_pulse_tick(state2, False)  # +1
    assert state2.pulse == 3
    engine.step_pulse_tick(state2, True)   # +1-1=净0
    assert state2.pulse == 3
    print("脉动步末测试通过")

    # 测试锋芒衰减
    state3 = BattleState(edge=2)
    engine.step_edge_decay(state3, False)  # 未进攻→-1
    assert state3.edge == 1
    engine.step_edge_decay(state3, True)   # 进攻→不衰减
    assert state3.edge == 1
    print("锋芒衰减测试通过")

    # 测试洞悉
    state4 = BattleState()
    engine.step_read_check(state4, CATEGORY_STRIKE, CATEGORY_STRIKE)  # 重复→+1
    assert state4.read == 1
    engine.step_read_check(state4, CATEGORY_GUARD, CATEGORY_STRIKE)   # 防御→+1
    assert state4.read == 2
    engine.step_read_check(state4, CATEGORY_FEINT, CATEGORY_STRIKE)   # 不重复非防御→不变
    assert state4.read == 2  # 已达上限
    print("洞悉检查测试通过")

    # 测试卡牌资源
    card_b01 = get_card("B01")  # 劈斩：进攻造成≥1伤害→锋芒+1
    state5 = BattleState()
    opponent5 = BattleState()
    logs = engine.apply_card_resources(card_b01, state5, opponent5, 2)
    assert state5.edge >= 1, f"劈斩应产生锋芒，实际{state5.edge}"
    print(f"卡牌资源测试通过: {logs}")

    print("\n所有资源引擎测试通过!")
