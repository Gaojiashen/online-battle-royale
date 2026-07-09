"""
战斗卡牌库 V6 —— 48张卡牌完整定义
从 docs/combat/generate_cards_v6.py 转录为 Python 数据结构

核心变更 V6：性相独占资源词条(锋芒/幻影/蓄力/寒意/脉动/洞悉)、
固定数值、无Lv缩放、等级成长=解锁新资源操作方式
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ════════════════════════════════════════════════════
# 常量
# ════════════════════════════════════════════════════

CATEGORY_STRIKE = "进攻"
CATEGORY_GUARD = "防御"
CATEGORY_FEINT = "佯攻"
CATEGORY_INTERRUPT = "打断"
CATEGORY_INVOKE = "状态"

ASPECT_BLADE = "刃"
ASPECT_MOTH = "蛾"
ASPECT_FORGE = "铸"
ASPECT_WINTER = "冬"
ASPECT_HEART = "心"
ASPECT_LANTERN = "灯"
ASPECT_GENERIC = "通用"

LVL_REQ = {0: "—", 2: "Lv2+", 6: "Lv6+", 10: "Lv10+", 15: "Lv15"}

# ════════════════════════════════════════════════════
# 卡牌数据模型
# ════════════════════════════════════════════════════

@dataclass
class Card:
    """单张战斗卡牌"""
    id: str                          # 编号 C01/B03/M07 等
    name: str                        # 卡名
    category: str                    # 进攻/防御/佯攻/打断/状态
    aspect: str                      # 刃/蛾/铸/冬/心/灯/通用
    level_requirement: int           # 等级门槛: 0=通用, 2/6/10/15
    base_damage: int = 0             # 固定基础伤害
    defense_value: int = 0           # 防御减免值
    effect_text: str = ""            # 完整效果文本
    resource_gen: Dict[str, int] = field(default_factory=dict)   # 生成的资源 {"锋芒":1, "寒意":1}
    resource_consume: Dict[str, object] = field(default_factory=dict)  # 消耗的资源 {"蓄力":"all", "洞悉":1}
    is_multi_hit: bool = False       # 是否连击
    hit_count: int = 1               # 击数
    applies_chill: bool = False      # 是否施加寒意
    chill_amount: int = 0            # 施加寒意层数
    bypasses_defense: bool = False   # 佯攻/光痕绕过防御
    interrupts_status: bool = False  # 打断类取消状态
    is_dodge: bool = False           # 闪避（伤害完全归零）
    is_illusion: bool = False        # 幻象（概率落空）
    probability: float = 1.0         # 效果概率（蛾幻象=0.5）
    heal_amount: int = 0             # 回复HP量
    shield_amount: int = 0           # 护盾量
    note: str = ""                   # 设计备注

    @property
    def level_text(self) -> str:
        return LVL_REQ.get(self.level_requirement, "—")

    @property
    def is_generic(self) -> bool:
        return self.aspect == ASPECT_GENERIC

    def player_can_use(self, aspect_levels: Dict[str, int]) -> bool:
        """判断玩家是否可用此牌（按多性相等级取并集）"""
        if self.is_generic:
            return True
        player_lv = aspect_levels.get(self.aspect, 0)
        return player_lv >= self.level_requirement


# ════════════════════════════════════════════════════
# 全部 48 张卡牌
# ════════════════════════════════════════════════════

ALL_CARDS: List[Card] = []
CARDS_BY_ID: Dict[str, Card] = {}


def _register(card: Card) -> Card:
    ALL_CARDS.append(card)
    CARDS_BY_ID[card.id] = card
    return card


# ═══════ 通用基础卡（Lv0+）6张 ═══════

_register(Card(
    id="C01", name="挥击", category=CATEGORY_STRIKE, aspect=ASPECT_GENERIC, level_requirement=0,
    base_damage=2,
    effect_text="造成 2 伤害。",
    note="最基础的进攻。任何时候、任何局面下都能用。"
))

_register(Card(
    id="C02", name="佯攻", category=CATEGORY_FEINT, aspect=ASPECT_GENERIC, level_requirement=0,
    base_damage=1, bypasses_defense=True,
    effect_text="造成 1 伤害。对手本步的「防御」行动被绕过（不减免本次伤害，不产生看破）。",
    note="克制防御的核心卡。伤害低但安全。"
))

_register(Card(
    id="C03", name="格挡", category=CATEGORY_GUARD, aspect=ASPECT_GENERIC, level_requirement=0,
    defense_value=2,
    effect_text="本步减免 2 伤害。若对手使用「进攻」→获得1层看破。",
    note="⚠ 不能连续使用。最基础的防御。"
))

_register(Card(
    id="C04", name="打断", category=CATEGORY_INTERRUPT, aspect=ASPECT_GENERIC, level_requirement=0,
    interrupts_status=True,
    effect_text="取消对手本步的「状态」行动。若对手本步使用的不是状态→此卡无效果。不造成伤害。",
    note="只做一件事：让对手的状态失效。"
))

_register(Card(
    id="C05", name="蓄势", category=CATEGORY_INVOKE, aspect=ASPECT_GENERIC, level_requirement=0,
    effect_text="下步进攻伤害+2。",
    note="简单直接。进攻前的一步铺垫。会被打断取消。"
))

_register(Card(
    id="C06", name="忍耐", category=CATEGORY_GUARD, aspect=ASPECT_GENERIC, level_requirement=0,
    defense_value=1,
    effect_text="本步减免 1 伤害。若对手使用「进攻」→获得1层看破。",
    note="⚠ 不能连续使用。减免比格挡少1，但保证触发看破。"
))

# ═══════ 刃 · BLADE（7张）— 锋芒 ═══════

_register(Card(
    id="B01", name="劈斩", category=CATEGORY_STRIKE, aspect=ASPECT_BLADE, level_requirement=2,
    base_damage=2,
    resource_gen={"锋芒": 1},
    effect_text="造成 2 伤害。获得 1 锋芒。",
    note="刃之基本功。每一刀都在积累锋芒。"
))

_register(Card(
    id="B02", name="刃之构", category=CATEGORY_INVOKE, aspect=ASPECT_BLADE, level_requirement=2,
    resource_gen={"锋芒": 2},
    effect_text="获得 2 锋芒。下步：你的进攻伤害无法被防御减免至1以下。",
    note="放弃本步伤害，快速叠满锋芒。会被打断取消。"
))

_register(Card(
    id="B03", name="连斩", category=CATEGORY_STRIKE, aspect=ASPECT_BLADE, level_requirement=6,
    base_damage=0, is_multi_hit=True, hit_count=2,
    resource_gen={"锋芒": 2},  # 每击命中→+1，两击全中=+2
    effect_text="连击(2次)。每击造成 1 伤害。每击命中→获得 1 锋芒。",
    note="双击穿透防御：第一击吃减免，第二击全额。看破翻倍全部击数。"
))

_register(Card(
    id="B04", name="斩法", category=CATEGORY_INTERRUPT, aspect=ASPECT_BLADE, level_requirement=6,
    base_damage=1, interrupts_status=True,
    resource_gen={"锋芒": 1},  # 成功取消状态→+1
    effect_text="造成 1 伤害。若对手本步使用「状态」→取消之，获得 1 锋芒。若对手未使用状态→仅造成伤害。",
    note="刃之道的打断。至少造成1伤害。取消状态还奖励锋芒。"
))

_register(Card(
    id="B05", name="万刃", category=CATEGORY_STRIKE, aspect=ASPECT_BLADE, level_requirement=10,
    base_damage=1,
    resource_consume={"锋芒": "all"},
    effect_text="消耗全部锋芒。造成 1 + [消耗数]×2 伤害。若消耗≥2层→本卡获得连击(2次)。",
    note="锋芒的终极释放。锋芒3→1+6=7伤害连击2次=14理论输出。"
))

_register(Card(
    id="B06", name="血刃", category=CATEGORY_STRIKE, aspect=ASPECT_BLADE, level_requirement=10,
    base_damage=2,
    resource_gen={"锋芒": 1},
    effect_text="造成 2 伤害。回复等于当前锋芒数的战斗HP。获得 1 锋芒。",
    note="续航。不消耗锋芒，只读取数值。与万刃形成爆发vs续航的选择。"
))

_register(Card(
    id="B07", name="斩界", category=CATEGORY_STRIKE, aspect=ASPECT_BLADE, level_requirement=15,
    base_damage=4,
    resource_consume={"锋芒": "all"},
    effect_text="造成 4 伤害。消耗全部锋芒，每层+3 伤害。使用后：剩余步无法使用任何行动（耗尽）。",
    note="一刀定生死。锋芒3→4+9=13伤害。耗尽=没有退路。"
))

# ═══════ 蛾 · MOTH（7张）— 幻影 ═══════

_register(Card(
    id="M01", name="闪避", category=CATEGORY_GUARD, aspect=ASPECT_MOTH, level_requirement=2,
    is_dodge=True,
    resource_gen={"幻影": 1},
    effect_text="完全避开对手本步的一次「进攻」。闪避成功→看破+1，幻影+1。",
    note="⚠ 不能连续使用。伤害归零+看破+幻影。"
))

_register(Card(
    id="M02", name="飞蛾扑火", category=CATEGORY_FEINT, aspect=ASPECT_MOTH, level_requirement=2,
    base_damage=1, bypasses_defense=True,
    resource_gen={"幻影": 1},
    effect_text="造成 1 伤害。若对手本步使用「防御」→绕过之，幻影+1+看破+1。",
    note="低风险获取幻影的手段。"
))

_register(Card(
    id="M03", name="蛾群幻象", category=CATEGORY_GUARD, aspect=ASPECT_MOTH, level_requirement=6,
    is_illusion=True, probability=0.5,
    resource_gen={"幻影": 1},
    resource_consume={"幻影": 2},  # 消耗2幻影→100%落空
    effect_text="对手本步行动50%概率落空。落空→看破+1，幻影+1。消耗 2 幻影→落空变为确定（100%）。",
    note="⚠ 不能连续使用。裸开=50%赌博。有2幻影=确定落空。"
))

_register(Card(
    id="M04", name="腐蝶", category=CATEGORY_INTERRUPT, aspect=ASPECT_MOTH, level_requirement=6,
    interrupts_status=True,
    effect_text="选择对手一步→若该步为「状态」卡：消耗 0 幻影→状态效果减半。消耗 1 幻影→改为打断（完全取消）。若该步非状态→无效果。",
    note="灵活的状态干扰。不消耗幻影也能削弱状态。"
))

_register(Card(
    id="M05", name="化身", category=CATEGORY_INVOKE, aspect=ASPECT_MOTH, level_requirement=10,
    resource_consume={"幻影": 2},
    effect_text="本步「不在场」：不受任何伤害和效果。消耗 2 幻影→下步闪避自动成功。",
    note="最强的规避——暂时退出战斗。会被打断取消。"
))

_register(Card(
    id="M06", name="蜕皮", category=CATEGORY_INVOKE, aspect=ASPECT_MOTH, level_requirement=10,
    heal_amount=3,
    resource_gen={"幻影": 1},
    resource_consume={"幻影": 1},  # 可选消耗
    effect_text="移除所有debuff。回复 3 HP。获得 1 幻影。消耗 1 幻影→回复 5 HP 代替。",
    note="回复+清debuff。会被打断取消。"
))

_register(Card(
    id="M07", name="最终蜕变", category=CATEGORY_INVOKE, aspect=ASPECT_MOTH, level_requirement=15,
    resource_consume={"幻影": "all"},
    effect_text="HP恢复至初始值的50%。移除所有debuff。消耗全部幻影，每层→剩余步中一次闪避自动成功。",
    note="蛾之飞升者蜕下旧皮囊。会被打断取消——必须在对手无打断能力时使用。"
))

# ═══════ 铸 · FORGE（7张）— 蓄力 ═══════

_register(Card(
    id="F01", name="锻体", category=CATEGORY_GUARD, aspect=ASPECT_FORGE, level_requirement=2,
    defense_value=2,
    resource_gen={"蓄力": 1},
    effect_text="本步减免 2 伤害。若对手使用「进攻」→看破+1，蓄力+1。",
    note="⚠ 不能连续使用。铸之核心防御。"
))

_register(Card(
    id="F02", name="铸甲", category=CATEGORY_INVOKE, aspect=ASPECT_FORGE, level_requirement=2,
    resource_gen={"蓄力": 1},
    effect_text="获得「铁甲」：下步受到的第一次伤害-2（可与防御减免叠加）。蓄力+1。",
    note="叠甲流。铁甲+下步防御=双重减免。会被打断取消。"
))

_register(Card(
    id="F03", name="锻炉之锤", category=CATEGORY_STRIKE, aspect=ASPECT_FORGE, level_requirement=6,
    base_damage=2,
    resource_consume={"蓄力": "all"},
    effect_text="造成 2 伤害。消耗全部蓄力，每层+2伤害。使用后：下步必须为防御或状态（不能进攻）。",
    note="铸的标准终结技。看破翻倍→16（蓄力3时）。但有收招硬直。"
))

_register(Card(
    id="F04", name="淬火", category=CATEGORY_INVOKE, aspect=ASPECT_FORGE, level_requirement=6,
    resource_gen={"蓄力": 2},
    effect_text="获得 2 蓄力。下步防御减免+2。",
    note="蓄力加速器。会被打断取消。"
))

_register(Card(
    id="F05", name="重铸", category=CATEGORY_INVOKE, aspect=ASPECT_FORGE, level_requirement=10,
    heal_amount=4,
    resource_gen={"蓄力": 2},
    effect_text="回复 4 HP。移除所有debuff。获得 2 蓄力。",
    note="一步三得。会被打断取消。"
))

_register(Card(
    id="F06", name="铁壁", category=CATEGORY_GUARD, aspect=ASPECT_FORGE, level_requirement=10,
    resource_gen={"蓄力": 2},
    effect_text="本步：所有受到的伤害减免至1（至少受1伤害）。减免后→看破+2，蓄力+2。",
    note="⚠ 不能连续使用。极限防御——无论多大伤害都只吃1点。但也送2看破给对手。"
))

_register(Card(
    id="F07", name="终极锻炉", category=CATEGORY_INVOKE, aspect=ASPECT_FORGE, level_requirement=15,
    base_damage=5,  # 下步伤害
    resource_consume={"蓄力": "all"},
    effect_text="本步：无敌（不受任何伤害和负面效果）。下步：造成 5 伤害，消耗全部蓄力（每层+2）。",
    note="两步合一的终极技。会被打断取消。"
))

# ═══════ 冬 · WINTER（7张）— 寒意 ═══════

_register(Card(
    id="W01", name="寒触", category=CATEGORY_STRIKE, aspect=ASPECT_WINTER, level_requirement=2,
    base_damage=1, applies_chill=True, chill_amount=1,
    effect_text="造成 1 伤害。对目标施加 1 寒意。",
    note="零限制，可反复使用。叠满3层触发处决。"
))

_register(Card(
    id="W02", name="寂灭之触", category=CATEGORY_INTERRUPT, aspect=ASPECT_WINTER, level_requirement=2,
    interrupts_status=True, applies_chill=True, chill_amount=1,
    effect_text="取消对手本步的「状态」行动。若成功取消→施加 1 寒意。若对手未使用状态→无效果。",
    note="冬之道的打断。成功取消状态还附赠寒意。"
))

_register(Card(
    id="W03", name="霜甲", category=CATEGORY_GUARD, aspect=ASPECT_WINTER, level_requirement=2,
    defense_value=2, applies_chill=True, chill_amount=1,
    effect_text="本步减免 2 伤害。若对手使用「进攻」→对攻击者施加 1 寒意。",
    note="⚠ 不能连续使用。防御+反伤寒意。"
))

_register(Card(
    id="W04", name="寂灭之息", category=CATEGORY_GUARD, aspect=ASPECT_WINTER, level_requirement=6,
    defense_value=3, applies_chill=True, chill_amount=1,
    effect_text="本步减免 3 伤害。看破+1。对对手施加 1 寒意。",
    note="⚠ 不能连续使用。强力防御+看破+寒意三合一。"
))

_register(Card(
    id="W05", name="凋零", category=CATEGORY_INVOKE, aspect=ASPECT_WINTER, level_requirement=6,
    effect_text="对手下步进攻伤害-2（不能低于1）。若对手身上寒意≥2层→改为-3。",
    note="削弱而非禁止。寒意越高效果越强。会被打断取消。"
))

_register(Card(
    id="W06", name="凛冬", category=CATEGORY_STRIKE, aspect=ASPECT_WINTER, level_requirement=10,
    base_damage=2, applies_chill=True, chill_amount=1,
    effect_text="造成 2 伤害。施加 1 寒意。若此时寒意达到3层→立即处决（本卡伤害翻倍）。",
    note="在对手寒意2层时使用→叠到3层→立即处决=4伤害。"
))

_register(Card(
    id="W07", name="终焉", category=CATEGORY_STRIKE, aspect=ASPECT_WINTER, level_requirement=15,
    base_damage=3, applies_chill=True, chill_amount=3,  # 直接设3层（覆盖）
    effect_text="造成 3 伤害。目标获得3层寒意（覆盖现有寒意值）。立即触发处决（本卡伤害翻倍→6伤害，寒意清零）。结算后：双方HP较低者HP归0。若相等→双方各-5HP。",
    note="冬之王亲自降临。后效判定：HP低者直接归0。"
))

# ═══════ 心 · HEART（7张）— 脉动 ═══════

_register(Card(
    id="H01", name="生命涌动", category=CATEGORY_INVOKE, aspect=ASPECT_HEART, level_requirement=2,
    heal_amount=2,
    resource_consume={"脉动": 1},
    effect_text="回复 2 HP。消耗 1 脉动→再回复 2 HP（总回复4HP）。",
    note="最可靠的回复。会被打断取消。"
))

_register(Card(
    id="H02", name="心之壁", category=CATEGORY_GUARD, aspect=ASPECT_HEART, level_requirement=2,
    defense_value=2,
    resource_gen={"脉动": 1},
    resource_consume={"脉动": 1},  # 可选
    shield_amount=2,
    effect_text="本步减免 2 伤害。减免后→获得 1 脉动。消耗 1 脉动→额外获得护盾2。",
    note="⚠ 不能连续使用。防御+脉动循环。"
))

_register(Card(
    id="H03", name="不屈", category=CATEGORY_GUARD, aspect=ASPECT_HEART, level_requirement=6,
    heal_amount=3,
    effect_text="本步若受致死伤害→HP锁定为1。触发后：回复 3 HP。消耗全部脉动，每层额外回复 1 HP。",
    note="⚠ 不能连续使用。残血不屈是最强威慑。"
))

_register(Card(
    id="H04", name="共鸣冲击", category=CATEGORY_STRIKE, aspect=ASPECT_HEART, level_requirement=6,
    base_damage=2,
    resource_consume={"脉动": 1},
    effect_text="造成 2 伤害。消耗 1 脉动→回复等于伤害量的HP。",
    note="吸血进攻。看破翻倍→伤害与回复同时翻倍。"
))

_register(Card(
    id="H05", name="心脏共鸣", category=CATEGORY_INVOKE, aspect=ASPECT_HEART, level_requirement=10,
    base_damage=2,
    resource_consume={"脉动": 1},
    shield_amount=4,
    effect_text="消耗 1 脉动→对手回复 2 HP，你获得护盾4。然后对对手造成 2 伤害。",
    note="先予后取。会被打断取消。"
))

_register(Card(
    id="H06", name="生命链接", category=CATEGORY_INVOKE, aspect=ASPECT_HEART, level_requirement=10,
    resource_consume={"脉动": 2},  # 可选消耗强化
    effect_text="选择下步或下下步→该步你受的所有伤害减半(向下取整)。消耗 2 脉动→改为减至1。",
    note="预判减伤。会被打断取消。"
))

_register(Card(
    id="H07", name="第二次心跳", category=CATEGORY_INVOKE, aspect=ASPECT_HEART, level_requirement=15,
    resource_consume={"脉动": "all"},
    effect_text="记录当前HP。若本场后续死亡→复活至记录HP+移除所有debuff。消耗全部脉动：每层使复活HP+2。复活后攻击力永久-2（本场）。",
    note="心之飞升者的终极保命。会被打断取消。"
))

# ═══════ 灯 · LANTERN（7张）— 洞悉 ═══════

_register(Card(
    id="L01", name="驱散", category=CATEGORY_INTERRUPT, aspect=ASPECT_LANTERN, level_requirement=2,
    interrupts_status=True,
    effect_text="取消对手本步的「状态」行动。若对手本步类别与上一步相同→获得 1 洞悉。",
    note="灯的打断附带模式观察。"
))

_register(Card(
    id="L02", name="洞见", category=CATEGORY_FEINT, aspect=ASPECT_LANTERN, level_requirement=2,
    base_damage=1, bypasses_defense=True,
    effect_text="造成 1 伤害。若对手本步使用的行动类别与上一步相同→伤害+2，获得 1 洞悉。",
    note="灯的核心卡。惩罚重复出牌。"
))

_register(Card(
    id="L03", name="光痕", category=CATEGORY_STRIKE, aspect=ASPECT_LANTERN, level_requirement=6,
    base_damage=2, bypasses_defense=True,
    effect_text="造成 2 伤害。若对手本步使用「防御」→防御被绕过（如同佯攻效果），获得 1 洞悉。",
    note="克制防御的进攻——呼应当'看穿防御'的主题。"
))

_register(Card(
    id="L04", name="闪光", category=CATEGORY_INVOKE, aspect=ASPECT_LANTERN, level_requirement=6,
    effect_text="若对手本步行动类别与上一步相同→其本步伤害/减免-2（不能低于1）。触发则获得 1 洞悉。",
    note="模式惩罚的防御面。会被打断取消。"
))

_register(Card(
    id="L05", name="残光", category=CATEGORY_FEINT, aspect=ASPECT_LANTERN, level_requirement=10,
    base_damage=1, bypasses_defense=True,
    resource_consume={"洞悉": 1},
    effect_text="造成 1 伤害。消耗 1 洞悉→本卡伤害 ×（消耗数+1）。即消耗1洞悉=×2，消耗2洞悉=×3。",
    note="灯的资源爆发。洞悉2→残光1×3=3伤害。"
))

_register(Card(
    id="L06", name="全视", category=CATEGORY_INVOKE, aspect=ASPECT_LANTERN, level_requirement=10,
    resource_consume={"洞悉": 2},
    effect_text="消耗 2 洞悉→查看对手剩余所有未揭示步的行动类别（进攻/防御/佯攻/打断/状态）。不揭示具体卡名。",
    note="信息即力量。会被打断取消。"
))

_register(Card(
    id="L07", name="揭示一切", category=CATEGORY_INVOKE, aspect=ASPECT_LANTERN, level_requirement=15,
    resource_consume={"洞悉": 2},
    effect_text="消耗 2 洞悉→选择对手一个未揭示步号，将其卡牌替换为你指定的一张通用基础卡（C01挥击/C02佯攻/C03格挡/C04打断）。",
    note="灯的终极飞升技。会被打断取消——对手打断的最高优先级目标。"
))


# ════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════

def get_card(card_id: str) -> Card:
    """通过ID获取卡牌"""
    if card_id not in CARDS_BY_ID:
        raise KeyError(f"未知卡牌ID: {card_id}")
    return CARDS_BY_ID[card_id]


def get_available_cards(aspect_levels: Dict[str, int]) -> List[Card]:
    """计算玩家可用卡牌：通用卡 + 各性相关卡牌（门槛≤等级）取并集"""
    available = []
    for card in ALL_CARDS:
        if card.player_can_use(aspect_levels):
            available.append(card)
    return available


def get_cards_by_category(cards: List[Card], category: str) -> List[Card]:
    """按类别过滤"""
    return [c for c in cards if c.category == category]


def get_cards_by_aspect(cards: List[Card], aspect: str) -> List[Card]:
    """按性相过滤"""
    return [c for c in cards if c.aspect == aspect]


# ════════════════════════════════════════════════════
# 统计信息
# ════════════════════════════════════════════════════

def print_stats():
    """打印卡牌统计"""
    cats = {}
    aspects = {}
    for c in ALL_CARDS:
        cats[c.category] = cats.get(c.category, 0) + 1
        if not c.is_generic:
            aspects[c.aspect] = aspects.get(c.aspect, 0) + 1
    generic = sum(1 for c in ALL_CARDS if c.is_generic)
    print(f"总卡牌: {len(ALL_CARDS)} ({generic} 通用 + {sum(aspects.values())} 性相)")
    print(f"类别分布: {cats}")
    print(f"性相分布: {aspects}")
    print(f"等级门槛分布: Lv0={sum(1 for c in ALL_CARDS if c.level_requirement==0)}, "
          f"Lv2={sum(1 for c in ALL_CARDS if c.level_requirement==2)}, "
          f"Lv6={sum(1 for c in ALL_CARDS if c.level_requirement==6)}, "
          f"Lv10={sum(1 for c in ALL_CARDS if c.level_requirement==10)}, "
          f"Lv15={sum(1 for c in ALL_CARDS if c.level_requirement==15)}")


if __name__ == "__main__":
    print_stats()

    # 示例：灯4+蛾6的可用牌
    example_levels = {"灯": 4, "蛾": 6}
    available = get_available_cards(example_levels)
    print(f"\n示例：灯4+蛾6 → 可用 {len(available)} 张牌:")
    for c in available:
        print(f"  {c.id} {c.name} ({c.aspect} {c.level_text})")
