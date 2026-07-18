"""
EventLog — JSONL 事件日志。

按 battle_id 分文件存储 BattleEvent 序列化记录。
用于崩溃恢复时的状态重建。

写入策略：
- write() + flush()，不 fsync()（微秒级，不阻塞 HTTP 热路径）
- 每个 battle 一个 .jsonl 文件
- 追加写（'a' mode），文件不存在自动创建
"""

import os
import json
import logging
from typing import List

from engine.events import BattleEvent

logger = logging.getLogger(__name__)


class EventLog:
    """
    JSONL 事件日志。

    目录结构:
      data/events/{battle_id}.jsonl

    每行一个 JSON 对象（BattleEvent.to_dict() 的结果）。
    用于崩溃恢复时重放事件。
    """

    def __init__(self, data_dir: str = "data/events"):
        self._data_dir = data_dir

    # ════════════════════════════════════════════════════
    # 公共接口
    # ════════════════════════════════════════════════════

    def append(self, event: BattleEvent) -> None:
        """
        同步追加一条事件到 {battle_id}.jsonl。

        只 write + flush，不 fsync。延迟 <1ms。
        异常不抛出，记录 CRITICAL 日志。
        """
        filepath = self._filepath(event.battle_id)
        try:
            line = json.dumps(event.to_dict(), ensure_ascii=False)
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except Exception:
            logger.critical(
                f"EventLog append failed: {event.event_id} "
                f"type={event.type.value} battle={event.battle_id}",
                exc_info=True,
            )

    def read(self, battle_id: str) -> List[BattleEvent]:
        """
        读取指定对战的所有事件（按写入顺序）。

        文件不存在返回空列表。
        解析失败的行跳过并记录 WARNING 日志。
        """
        filepath = self._filepath(battle_id)
        if not os.path.exists(filepath):
            return []

        events = []
        with open(filepath, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    event = BattleEvent.from_dict(d)
                    events.append(event)
                except Exception:
                    logger.warning(
                        f"EventLog skip corrupted line: {filepath}:{lineno}",
                        exc_info=True,
                    )
        return events

    def delete(self, battle_id: str) -> None:
        """
        删除指定对战的 event log。

        对战结束后清理，释放磁盘空间。
        文件不存在时静默跳过。
        """
        filepath = self._filepath(battle_id)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"EventLog deleted: {battle_id}")
        except OSError:
            logger.warning(
                f"EventLog delete failed: {battle_id}", exc_info=True
            )

    # ════════════════════════════════════════════════════
    # 内部
    # ════════════════════════════════════════════════════

    def _filepath(self, battle_id: str) -> str:
        """返回 battle 对应的 JSONL 文件路径，自动创建目录"""
        os.makedirs(self._data_dir, exist_ok=True)
        return os.path.join(self._data_dir, f"{battle_id}.jsonl")
