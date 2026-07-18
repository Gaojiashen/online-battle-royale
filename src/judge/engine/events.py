"""
战斗事件定义 — 纯数据层，零外部依赖。

定义在 engine/ 层：
- 不导入 asyncio
- 不导入 HTTP / Feishu / WebSocket
- EventBus 只是 Protocol，不包含实现
- BattleManager 只依赖 EventBus Protocol
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Protocol
from enum import Enum
import uuid
import time


# ════════════════════════════════════════════════════
# 事件类型枚举
# ════════════════════════════════════════════════════

class BattleEventType(str, Enum):
    """战斗事件类型"""
    BATTLE_CREATED  = "battle_created"     # 对战初始化（init_battle）
    BATTLE_RESTORED = "battle_restored"    # 会话从 Base 恢复（restore_*）
    DECK_CONFIRMED  = "deck_confirmed"     # 双方牌库锁定，对战正式开始
    CARD_SUBMITTED  = "card_submitted"     # 玩家提交出牌（可能未结算）
    ROUND_RESOLVED  = "round_resolved"     # 回合结算完成
    BATTLE_FINISHED = "battle_finished"    # 对战结束
    BATTLE_ERROR    = "battle_error"       # 状态变更异常


# ════════════════════════════════════════════════════
# 事件数据类
# ════════════════════════════════════════════════════

@dataclass(frozen=True)
class BattleEvent:
    """
    不可变战斗事件。

    frozen=True 保证事件发布后不可被订阅方篡改。
    event_id 全局唯一标识，用于日志关联和去重。
    retry_count / max_retries 由 EventBus 消费端管理。
    schema_version 标识事件格式版本，用于未来迁移。

    序列化：to_dict() → json.dumps() → JSONL/网络传输
    反序列化：json.loads() → from_dict() → BattleEvent
    """

    event_id: str
    type: BattleEventType
    battle_id: str
    timestamp: float
    data: Dict[str, Any]
    retry_count: int = 0
    max_retries: int = 3
    schema_version: int = 1

    @classmethod
    def create(
        cls,
        event_type: BattleEventType,
        battle_id: str,
        data: Dict[str, Any],
        max_retries: int = 3,
    ) -> "BattleEvent":
        """工厂方法 — 自动生成 event_id 和 timestamp"""
        return cls(
            event_id=str(uuid.uuid4()),
            type=event_type,
            battle_id=battle_id,
            timestamp=time.time(),
            data=data,
            retry_count=0,
            max_retries=max_retries,
        )

    def for_retry(self) -> "BattleEvent":
        """生成重试事件 — 复用 event_id，递增 retry_count"""
        return BattleEvent(
            event_id=self.event_id,
            type=self.type,
            battle_id=self.battle_id,
            timestamp=self.timestamp,
            data=self.data,
            retry_count=self.retry_count + 1,
            max_retries=self.max_retries,
            schema_version=self.schema_version,
        )

    # ════════════════════════════════════════════════════
    # 序列化 / 反序列化
    # ════════════════════════════════════════════════════

    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为 JSON 兼容的 dict。

        Enum 转 .value (str)，所有 data 字段均为原生 Python 类型。
        data 不做深层转换——由 BattleManager 保证其 JSON 兼容性。
        """
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "type": self.type.value,
            "battle_id": self.battle_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BattleEvent":
        """
        从 dict 反序列化。

        兼容旧格式（无 schema_version 默认 v1）。
        """
        return cls(
            event_id=d["event_id"],
            type=BattleEventType(d["type"]),
            battle_id=d["battle_id"],
            timestamp=d["timestamp"],
            data=d["data"],
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
            schema_version=d.get("schema_version", 1),
        )


# ════════════════════════════════════════════════════
# EventBus 协议
# ════════════════════════════════════════════════════

class EventBus(Protocol):
    """
    事件总线协议。

    emit() 是同步方法 — BattleManager 调用后立即返回，
    不知道也不关心谁消费事件、何时消费、是否成功。
    """

    def emit(self, event: BattleEvent) -> None:
        """
        发布事件。同步调用，立即返回。

        实现侧（AsyncEventBus）将事件放入 asyncio.Queue，
        后台消费者异步处理。此方法不抛出异常（失败由消费者记录）。
        """
        ...

    def subscribe(
        self,
        event_type: BattleEventType,
        handler: Callable[[BattleEvent], Any],
    ) -> None:
        """
        注册事件处理器。

        handler 签名为 (BattleEvent) -> Any。
        同步 handler 返回 None，异步 handler 返回 Coroutine。
        EventBus 实现负责 await 返回值为 Coroutine 的 handler。
        """
        ...


# ════════════════════════════════════════════════════
# 空实现（NOP — 测试/开发环境使用）
# ════════════════════════════════════════════════════

class NullEventBus:
    """
    空事件总线 — 所有操作都是 no-op。

    用于测试环境和向后兼容（BattleManager(event_bus=None) 的默认行为）。
    """

    def emit(self, event: BattleEvent) -> None:
        pass

    def subscribe(
        self,
        event_type: BattleEventType,
        handler: Callable[[BattleEvent], Any],
    ) -> None:
        pass
