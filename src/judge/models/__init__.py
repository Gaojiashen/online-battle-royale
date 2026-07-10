"""
Models — re-exports for backward-compatible imports.

Usage: from models import BattleInitRequest, CardInfo, ...
"""
from .requests import (
    BattleInitRequest,
    DeckConfirmRequest,
    InitFromBaseRequest,
    ConfirmFromBaseRequest,
    WebhookPayload,
)
from .responses import (
    CardInfo,
    BattleInitResponse,
    DeckConfirmResponse,
    RoundLog,
    WebhookResponse,
    PlayerStateInfo,
    BattleStatusResponse,
    BattleHistoryResponse,
)
from .player_requests import (
    SelectDeckRequest,
    SubmitCardRequest,
)
from .player_responses import (
    PlayerLookupResponse,
    PlayerBattleResponse,
    AvailableCard,
    AvailableCardsResponse,
    SelectDeckResponse,
    SubmitCardResponse,
    RoundResultInfo,
    BattleLogEntry,
    BattleLogsResponse,
)
