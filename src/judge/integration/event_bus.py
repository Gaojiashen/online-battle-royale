"""
AsyncEventBus — 基于 asyncio.Queue 的后台事件总线。

架构:
  BattleManager.emit() ──put_nowait()──▶ asyncio.Queue ──get()──▶ _consume_loop()
                                                                      │
                                                               dispatch → handler(event)
                                                                      │
                                                               await handler (async def)
                                                                      │
                                                               失败? → retry (指数退避)

emit() 同步非阻塞，put_nowait 不返回 coroutine。
_consume_loop 作为 asyncio.Task 在后台运行。
包含 3 次指数退避重试。
"""

import asyncio
import logging
from typing import Dict, List, Callable, Optional

from engine.events import BattleEvent, BattleEventType, EventBus
from integration.event_log import EventLog
from integration.dead_letter import DeadLetterQueue
from integration.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class AsyncEventBus:
    """
    生产级事件总线。

    使用 asyncio.Queue 实现生产者-消费者模式：
    - emit() 是同步的（put_nowait），不阻塞 BattleManager
    - _consume_loop 是后台 asyncio.Task，负责调度 handler
    - 失败的 handler 自动重试（最多 3 次，指数退避）
    """

    def __init__(self, queue_size: int = 256, event_log: EventLog = None,
                 dead_letter_queue: DeadLetterQueue = None,
                 websocket_manager: WebSocketManager = None):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._handlers: Dict[str, List[Callable]] = {}
        self._consumer_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._event_log: EventLog = event_log if event_log is not None else EventLog()
        self._dead_letter: DeadLetterQueue = (
            dead_letter_queue if dead_letter_queue is not None else DeadLetterQueue()
        )
        self._ws_manager: Optional[WebSocketManager] = websocket_manager

    # ════════════════════════════════════════════════════
    # EventBus Protocol 实现
    # ════════════════════════════════════════════════════

    def emit(self, event: BattleEvent) -> None:
        """
        同步非阻塞发布事件。

        1. 先写入 EventLog（持久化，保证不丢失）
        2. 再放入 asyncio.Queue（后台消费）

        EventLog.append() 是同步本地文件写，延迟 <1ms。
        如果队列满（消费者严重滞后），丢弃事件并记录 CRITICAL 日志。
        """
        # 先持久化到 event log — 保证即使进程崩溃也能恢复
        self._event_log.append(event)

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.critical(
                f"EventBus queue FULL (max={self._queue.maxsize} "
                f"qsize={self._queue.qsize()}) — "
                f"dropping event: {event.event_id} type={event.type.value} "
                f"battle={event.battle_id}"
            )

    def subscribe(
        self,
        event_type: BattleEventType,
        handler: Callable[[BattleEvent], None],
    ) -> None:
        """注册事件处理器"""
        key = event_type.value
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)

    # ════════════════════════════════════════════════════
    # 生命周期
    # ════════════════════════════════════════════════════

    async def start(self) -> None:
        """
        启动后台消费者。

        由 app.py lifespan 在 yield 之前调用，
        确保第一条请求到达时消费者已在运行。
        """
        if self._running:
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("AsyncEventBus consumer started")

    async def stop(self) -> None:
        """
        优雅关闭：停止消费者，排空队列中剩余事件。

        由 app.py lifespan 在 yield 之后调用（shutdown 阶段）。
        """
        if not self._running:
            return

        self._running = False

        # 取消消费者循环
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # 排空队列中未处理的事件
        drained = 0
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                await self._dispatch_event(event)
                self._queue.task_done()
                drained += 1
            except asyncio.QueueEmpty:
                break

        logger.info(f"AsyncEventBus stopped (drained {drained} pending events)")

    # ════════════════════════════════════════════════════
    # 消费者循环
    # ════════════════════════════════════════════════════

    async def _consume_loop(self) -> None:
        """后台事件消费者 — 无界循环，从队列取事件并分发"""
        while self._running:
            try:
                # 1 秒超时，允许定期检查 _running 标志
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch_event(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("EventBus consumer loop unexpected error")

    async def _dispatch_event(self, event: BattleEvent) -> None:
        """分发单个事件到所有注册的 handler"""
        # Phase 3: WebSocket 实时推送（先于持久化，失败不影响后续）
        if self._ws_manager is not None:
            try:
                await self._ws_manager.broadcast(event.battle_id, event)
            except Exception:
                logger.error(
                    f"WebSocket broadcast failed for {event.event_id} "
                    f"type={event.type.value}",
                    exc_info=True,
                )

        handlers = self._handlers.get(event.type.value, [])
        if not handlers:
            logger.debug(f"No handlers for event type: {event.type.value}")
            return

        for handler in handlers:
            try:
                result = handler(event)
                # handler 返回 coroutine 则 await
                if result is not None:
                    await result
                logger.debug(
                    f"Event handled: {event.event_id} type={event.type.value} "
                    f"handler={handler.__name__}"
                )
            except Exception:
                logger.error(
                    f"Handler failed for event {event.event_id} "
                    f"type={event.type.value} handler={handler.__name__}",
                    exc_info=True,
                )
                await self._maybe_retry(event)

    async def _maybe_retry(self, event: BattleEvent) -> None:
        """
        指数退避重试。

        1 秒 → 2 秒 → 4 秒。
        超过 max_retries 后记录 CRITICAL 并丢弃。
        （Phase 2: 失败事件写入死信队列。）
        """
        if event.retry_count >= event.max_retries:
            error_msg = (
                f"Handler failed after {event.max_retries} retries for "
                f"event {event.event_id} type={event.type.value} "
                f"battle={event.battle_id}"
            )
            logger.critical(error_msg)
            # 写入死信队列，供后续人工补偿
            self._dead_letter.append(event, error_msg)
            return

        delay = 2 ** event.retry_count  # 1s, 2s, 4s
        logger.warning(
            f"Retrying event {event.event_id} type={event.type.value} "
            f"battle={event.battle_id} "
            f"(attempt {event.retry_count + 1}/{event.max_retries}) "
            f"after {delay}s"
        )
        await asyncio.sleep(delay)

        retry_event = event.for_retry()
        try:
            self._queue.put_nowait(retry_event)
        except asyncio.QueueFull:
            logger.critical(
                f"Queue full during retry (max={self._queue.maxsize} "
                f"qsize={self._queue.qsize()}) — "
                f"dropping event: {event.event_id} type={event.type.value} "
                f"battle={event.battle_id}"
            )
