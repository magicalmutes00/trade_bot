"""Push dispatch: sender abstraction + eligibility-driven fan-out.

Senders:
- ``FcmSender``      â€” real Firebase Cloud Messaging (Admin SDK messaging).
- ``LogSender``      â€” development fallback; logs instead of sending so the
                       pipeline works end-to-end without Firebase credentials.

The dispatcher never raises on individual send failures â€” delivery is
best-effort by design.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.firebase import is_configured
from app.core.logging import get_logger
from app.repositories.notification_repository import NotificationRepository
from app.models import Signal, Instrument

logger = get_logger(__name__)


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    data: dict[str, str]


class Sender(Protocol):
    async def send(self, tokens: list[str], message: PushMessage) -> int: ...


class LogSender:
    name = "log"

    async def send(self, tokens: list[str], message: PushMessage) -> int:
        logger.info("[push:dev] would send to %d device(s): %s | %s",
                    len(tokens), message.title, message.body)
        return len(tokens)


class FcmSender:
    name = "fcm"

    async def send(self, tokens: list[str], message: PushMessage) -> int:
        from firebase_admin import messaging

        if not tokens:
            return 0
        msg = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=message.title, body=message.body),
            data={k: str(v) for k, v in message.data.items()},
            android=messaging.AndroidConfig(priority="high"),
        )
        try:
            response = messaging.send_each_for_multicast(msg)
        except Exception:
            logger.exception("FCM multicast failed")
            return 0
        ok = response.success_count
        if response.failure_count:
            logger.info("FCM partial failure: %d/%d", response.failure_count, len(tokens))
        return ok


def build_sender() -> Sender:
    return FcmSender() if is_configured() else LogSender()


def compose_signal_message(signal: Signal, instrument: Instrument) -> PushMessage:  # noqa: ANN001
    direction = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
    strength = signal.strength.value if hasattr(signal.strength, "value") else signal.strength
    tf = signal.timeframe.value if hasattr(signal.timeframe, "value") else signal.timeframe
    arrow = "â–²" if direction == "BULLISH" else "â–¼"
    return PushMessage(
        title=f"{arrow} BOF {direction.capitalize()} â€” {instrument.symbol}",
        body=f"{strength.replace('_', ' ').title()} breakout failure on the {tf} chart",
        data={
            "type": "bof_signal",
            "signal_id": str(signal.id),
            "instrument_id": str(instrument.id),
            "symbol": instrument.symbol,
            "direction": direction,
            "strength": strength,
        },
    )


class NotificationDispatcher:
    def __init__(self, db: AsyncSession, sender: Sender | None = None) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.sender = sender or build_sender()

    async def notify_new_signal(self, signal: Signal, instrument: Instrument) -> int:  # noqa: ANN001
        direction = signal.direction.value if hasattr(signal.direction, "value") else signal.direction
        strength = signal.strength.value if hasattr(signal.strength, "value") else signal.strength

        deliveries = await self.repo.eligible_deliveries(
            direction=direction,
            strength_value=_rank(strength),
            instrument_id=instrument.id,
        )
        if not deliveries:
            return 0

        tokens = [t.fcm_token for _, t in deliveries]
        message = compose_signal_message(signal, instrument)

        sent = await self.sender.send(tokens, message)
        logger.info("push '%s' delivered to %d/%d devices via %s",
                    message.title, sent, len(tokens), self.sender.name)
        return sent

    async def notify_market_status(self, market: str, status: str) -> int:
        """Broadcast to every active token of users with push_enabled."""
        rows = (
            await self.db.execute(_active_tokens_query())
        ).scalars().all()
        if not rows:
            return 0
        message = PushMessage(
            title="Market update",
            body=f"{market} is now {status.replace('_', ' ').lower()}",
            data={"type": "market_status", "market": market, "status": status},
        )
        return await self.sender.send([r.fcm_token for r in rows], message)


async def send_test_push(db: AsyncSession, user_id: uuid.UUID, *, symbol: str = "TCS") -> int:
    """CLI helper â€” one synthetic push to every active device of a user."""
    repo = NotificationRepository(db)
    tokens = [t.fcm_token for t in await repo.active_tokens_for_user(user_id)]
    if not tokens:
        return 0
    sender = build_sender()
    msg = PushMessage(
        title="BOF Edge test push",
        body=f"If you can read this, notifications work. ({symbol})",
        data={"type": "test"},
    )
    return await sender.send(tokens, msg)


def _rank(name: str) -> int:
    from app.repositories.notification_repository import _strength_rank

    return _strength_rank(name)


def _active_tokens_query():
    from sqlalchemy import select

    from app.models import NotificationPreference, NotificationToken

    return (
        select(NotificationToken)
        .join(NotificationPreference,
              NotificationPreference.user_id == NotificationToken.user_id)
        .where(
            NotificationPreference.push_enabled.is_(True),
            NotificationToken.is_active.is_(True),
        )
    )


__all__ = [
    "NotificationDispatcher", "LogSender", "FcmSender", "build_sender",
    "compose_signal_message", "send_test_push", "PushMessage",
]

