"""
组牌校验器 — 多性相可用牌计算 + 8张组牌校验

规则：
- 可用牌 = 通用卡(C01-C06) + 各性相关卡牌(门槛≤玩家该性相等级)取并集
- 战前从可用牌中选8张作为本场牌库
- 每回合从8张中选1张出牌
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from engine.card_library import (
    Card, ALL_CARDS, CARDS_BY_ID, get_available_cards,
    ASPECT_BLADE, ASPECT_MOTH, ASPECT_FORGE, ASPECT_WINTER, ASPECT_HEART, ASPECT_LANTERN
)

# 本场牌库大小
DECK_SIZE = 8  # 最大牌库数量（可选 1-8 张）

# 所有性相列表
ALL_ASPECTS = [ASPECT_BLADE, ASPECT_MOTH, ASPECT_FORGE, ASPECT_WINTER, ASPECT_HEART, ASPECT_LANTERN]


@dataclass
class DeckValidationResult:
    """组牌校验结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    selected_cards: List[Card] = field(default_factory=list)


def calculate_available(aspect_levels: Dict[str, int]) -> List[Card]:
    """
    计算玩家可用卡牌（多性相取并集）

    例：{"灯": 4, "蛾": 6}
    → C01-C06 + 灯Lv2+灯Lv4 + 蛾Lv2+蛾Lv6

    Args:
        aspect_levels: {性相: 等级}，未出现的性相等级视为0

    Returns:
        可用卡牌列表
    """
    return get_available_cards(aspect_levels)


def calculate_available_ids(aspect_levels: Dict[str, int]) -> Set[str]:
    """返回可用卡牌ID集合"""
    return {c.id for c in calculate_available(aspect_levels)}


def validate_deck(selected_card_ids: List[str], aspect_levels: Dict[str, int]) -> DeckValidationResult:
    """
    验证8张组牌是否合法

    规则：
    1. 必须正好选8张
    2. 每张牌必须在玩家可用范围内
    3. 不能重复选择同一张牌

    Args:
        selected_card_ids: 选中的卡牌ID列表
        aspect_levels: 玩家各性相等级

    Returns:
        DeckValidationResult
    """
    errors = []
    warnings = []
    selected_cards = []

    # 检查数量
    if len(selected_card_ids) > DECK_SIZE:
        errors.append(f"最多选择 {DECK_SIZE} 张牌，当前选择了 {len(selected_card_ids)} 张")
    if len(selected_card_ids) == 0:
        errors.append("至少选择 1 张牌")

    # 检查重复
    seen = set()
    duplicates = set()
    for cid in selected_card_ids:
        if cid in seen:
            duplicates.add(cid)
        seen.add(cid)
    if duplicates:
        errors.append(f"以下卡牌重复选择: {', '.join(duplicates)}")

    # 检查每张牌是否可用
    available_ids = calculate_available_ids(aspect_levels)
    for cid in selected_card_ids:
        if cid not in available_ids:
            card = CARDS_BY_ID.get(cid)
            if card:
                errors.append(
                    f"{card.id} {card.name} 不可用：需要 {card.aspect} {card.level_text}，"
                    f"当前{card.aspect}等级={aspect_levels.get(card.aspect, 0)}"
                )
            else:
                errors.append(f"未知卡牌ID: {cid}")
        else:
            selected_cards.append(CARDS_BY_ID[cid])

    # 战术建议（warnings，不影响合法性）
    categories = [c.category for c in selected_cards]
    from engine.card_library import CATEGORY_STRIKE, CATEGORY_GUARD, CATEGORY_FEINT, CATEGORY_INTERRUPT, CATEGORY_INVOKE

    strike_count = categories.count(CATEGORY_STRIKE)
    guard_count = categories.count(CATEGORY_GUARD)

    if strike_count == 0:
        warnings.append("牌库中没有进攻卡牌，可能无法有效造成伤害")
    if guard_count == 0:
        warnings.append("牌库中没有防御卡牌，对手进攻时将无法减免伤害")
    if strike_count > 5:
        warnings.append("进攻卡牌占比过高，考虑加入一些防御或状态牌")

    is_valid = len(errors) == 0

    return DeckValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        selected_cards=selected_cards if is_valid else []
    )


def get_available_by_aspect(aspect_levels: Dict[str, int]) -> Dict[str, List[Card]]:
    """按性相分组返回可用卡牌"""
    available = calculate_available(aspect_levels)
    grouped = {"通用": []}
    for aspect in ALL_ASPECTS:
        grouped[aspect] = []
    for card in available:
        if card.is_generic:
            grouped["通用"].append(card)
        else:
            grouped[card.aspect].append(card)
    return grouped


def get_aspect_summary(aspect_levels: Dict[str, int]) -> Dict[str, dict]:
    """
    获取各性相的可用卡牌摘要

    Returns:
        {性相: {"level": 等级, "count": 可用数, "cards": [卡名列表]}}
    """
    available = calculate_available(aspect_levels)
    summary = {}
    for aspect in ALL_ASPECTS:
        aspect_cards = [c for c in available if c.aspect == aspect]
        summary[aspect] = {
            "level": aspect_levels.get(aspect, 0),
            "count": len(aspect_cards),
            "cards": [f"{c.id} {c.name}" for c in aspect_cards]
        }
    generic_cards = [c for c in available if c.is_generic]
    summary["通用"] = {
        "level": 0,
        "count": len(generic_cards),
        "cards": [f"{c.id} {c.name}" for c in generic_cards]
    }
    return summary


def suggest_deck(aspect_levels: Dict[str, int], strategy: str = "balanced") -> List[str]:
    """
    根据策略自动推荐8张牌

    Args:
        aspect_levels: 玩家性相等级
        strategy: "balanced"(均衡), "aggressive"(进攻), "defensive"(防守), "control"(控制)

    Returns:
        推荐的8张卡牌ID
    """
    available = calculate_available(aspect_levels)

    from engine.card_library import CATEGORY_STRIKE, CATEGORY_GUARD, CATEGORY_FEINT, CATEGORY_INTERRUPT, CATEGORY_INVOKE

    strikes = [c for c in available if c.category == CATEGORY_STRIKE]
    guards = [c for c in available if c.category == CATEGORY_GUARD]
    feints = [c for c in available if c.category == CATEGORY_FEINT]
    interrupts = [c for c in available if c.category == CATEGORY_INTERRUPT]
    invokes = [c for c in available if c.category == CATEGORY_INVOKE]

    # 按等级排序（高级牌优先）
    def sort_key(c): return (-c.level_requirement, c.id)
    for lst in [strikes, guards, feints, interrupts, invokes]:
        lst.sort(key=sort_key)

    deck_ids = []

    if strategy == "aggressive":
        # 5进攻 1防御 1佯攻 1打断
        deck_ids.extend([c.id for c in strikes[:5]])
        deck_ids.extend([c.id for c in guards[:1]])
        deck_ids.extend([c.id for c in feints[:1]])
        deck_ids.extend([c.id for c in interrupts[:1]])
    elif strategy == "defensive":
        # 3防御 2进攻 1佯攻 1状态 1打断
        deck_ids.extend([c.id for c in guards[:3]])
        deck_ids.extend([c.id for c in strikes[:2]])
        deck_ids.extend([c.id for c in feints[:1]])
        deck_ids.extend([c.id for c in invokes[:1]])
        deck_ids.extend([c.id for c in interrupts[:1]])
    elif strategy == "control":
        # 2进攻 2防御 2打断 2状态
        deck_ids.extend([c.id for c in strikes[:2]])
        deck_ids.extend([c.id for c in guards[:2]])
        deck_ids.extend([c.id for c in interrupts[:2]])
        deck_ids.extend([c.id for c in invokes[:2]])
    else:  # balanced
        # 3进攻 2防御 1佯攻 1打断 1状态
        deck_ids.extend([c.id for c in strikes[:3]])
        deck_ids.extend([c.id for c in guards[:2]])
        deck_ids.extend([c.id for c in feints[:1]])
        deck_ids.extend([c.id for c in interrupts[:1]])
        deck_ids.extend([c.id for c in invokes[:1]])

    # 补齐到8张（如果某类别不够）
    remaining = [c for c in available if c.id not in deck_ids]
    remaining.sort(key=sort_key)
    while len(deck_ids) < DECK_SIZE and remaining:
        deck_ids.append(remaining.pop(0).id)

    return deck_ids[:DECK_SIZE]


# ════════════════════════════════════════════════════
# 测试
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    # 示例：灯4蛾6
    levels = {"灯": 4, "蛾": 6}
    available = calculate_available(levels)
    print(f"灯4+蛾6 → 可用 {len(available)} 张牌:")
    grouped = get_available_by_aspect(levels)
    for aspect, cards in grouped.items():
        if cards:
            names = ", ".join(f"{c.id} {c.name}" for c in cards)
            print(f"  [{aspect}] {names}")

    print(f"\n性相摘要:")
    summary = get_aspect_summary(levels)
    for aspect, info in summary.items():
        if info["count"] > 0:
            print(f"  {aspect}(Lv{info['level']}): {info['count']}张 - {', '.join(info['cards'])}")

    # 测试组牌校验
    print(f"\n=== 组牌校验测试 ===")

    # 合法组牌
    valid_deck = ["C01", "C02", "C03", "C04", "M01", "M02", "L01", "L02"]
    result = validate_deck(valid_deck, levels)
    print(f"合法组牌 ({len(valid_deck)}张): {result.is_valid}")
    if result.warnings:
        for w in result.warnings:
            print(f"  [!] {w}")

    # 非法：数量不够
    too_few = ["C01", "C02", "C03"]
    result = validate_deck(too_few, levels)
    print(f"\n数量不足 ({len(too_few)}张): {result.is_valid}")
    for e in result.errors:
        print(f"  [X] {e}")

    # 非法：超出等级
    too_high = ["C01", "C02", "C03", "C04", "C05", "C06", "L03", "L04"]  # L03需要灯6
    result = validate_deck(too_high, levels)
    print(f"\n超出等级: {result.is_valid}")
    for e in result.errors:
        print(f"  [X] {e}")

    # 自动推荐
    print(f"\n=== 自动推荐8张牌 ===")
    for strategy in ["balanced", "aggressive", "defensive", "control"]:
        deck = suggest_deck(levels, strategy)
        names = [f"{cid} {CARDS_BY_ID[cid].name}" for cid in deck]
        print(f"  {strategy}: {', '.join(names)}")
