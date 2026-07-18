"""
DeadLetterQueue — 死信队列。

保存 3 次重试后仍然失败的 BattleEvent。
JSONL 格式，所有失败事件共用一个文件。
供人工排查和数据补偿。
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from engine.events import BattleEvent

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """
    死信队列。

    文件: data/dead_letters/dead_letters.jsonl

    每行一个 JSON 对象:
      {"event_id","event_type","battle_id","data","error","failed_at","retry_count"}
    """

    def __init__(self, path: str = "data/dead_letters/dead_letters.jsonl"):
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    # ════════════════════════════════════════════════════
    # 公共接口
    # ════════════════════════════════════════════════════

    def append(self, event: BattleEvent, error: str) -> None:
        """
        追加一条死信记录。

        异常不抛出，记录 CRITICAL 日志。
        """
        try:
            record = {
                "event_id": event.event_id,
                "event_type": event.type.value,
                "battle_id": event.battle_id,
                "data": event.data,
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "retry_count": event.retry_count,
            }
            line = json.dumps(record, ensure_ascii=False)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except Exception:
            logger.critical(
                f"DeadLetterQueue append failed: {event.event_id} "
                f"type={event.type.value} battle={event.battle_id}",
                exc_info=True,
            )

    def read_all(self) -> List[Dict[str, Any]]:
        """
        读取所有死信记录。

        文件不存在返回空列表。
        解析失败的行跳过并记录 WARNING。
        """
        if not os.path.exists(self._path):
            return []

        records = []
        with open(self._path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        f"DeadLetterQueue skip corrupted line: "
                        f"{self._path}:{lineno}"
                    )
        return records

    def remove(self, event_id: str) -> None:
        """
        删除指定 event_id 的死信记录。

        重写整个文件（跳过匹配的行）。
        死信量极小（正常为零），性能可接受。
        """
        if not os.path.exists(self._path):
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            removed = False
            with open(self._path, "w", encoding="utf-8") as f:
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                        if record.get("event_id") == event_id:
                            removed = True
                            continue  # skip this line
                    except json.JSONDecodeError:
                        pass  # keep corrupted lines
                    f.write(line)

            if removed:
                logger.info(f"DeadLetterQueue removed: {event_id}")
        except OSError:
            logger.warning(
                f"DeadLetterQueue remove failed: {event_id}", exc_info=True
            )
