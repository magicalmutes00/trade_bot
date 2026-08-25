"""Phase 6 tests â€” token registration, preference matrix, dispatcher fan-out.

No real FCM calls: the dispatcher is exercised with a recording fake sender.
"""

import uuid

from app.models import (
    Instrument,
    InstrumentType,
    NotificationPreference,
    NotificationToken,
)
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_service import (
    LogSender,
    NotificationDispatcher,
    PushMessage,
)


class RecordingSender:
    name = "recording"

    def __init__(self) -> None:
        self.sent: list[tuple[list[str], PushMessage]] = []

    async def send(self, tokens, message):
        self.sent.append((list(tokens), message))
        return len(tokens)


async def _mk_user_with_device(client, *, email="pusher@example.com", token="fcm-token-aaa-111"):
    from tests.conftest import auth_headers, login_user, register_user

    await register_user(client, email=email, password="PushPass123", username=email.split("@")[0])
    tokens = await login_user(client, email=email, password="PushPass123")
    h = auth_headers(tokens)

    resp = await client.post(
        "/api/v1/notifications/tokens",
        json={"fcm_token": token, "platform": "ANDROID"},
        headers=h,
    )
    assert resp.status_code == 201
    return h, token


async def test_register_token_and_dedupe(client, db):
    h, token = await _mk_user_with_device(client)

    # same token again â†’ upsert, not duplicate
    r2 = await client.post("/api/v1/notifications/tokens",
                           json={"fcm_token": token}, headers=h)
    assert r2.status_code == 201

    overview = (await client.get("/api/v1/notifications", headers=h)).json()["data"]
    assert len(overview["tokens"]) == 1
    assert overview["tokens"][0]["is_active"] is True


async def test_preferences_defaults_then_patch(client):
    h, _ = await _mk_user_with_device(client)

    prefs = (await client.get("/api/v1/notifications/preferences", headers=h)).json()["data"]
    assert prefs["push_enabled"] is True
    assert prefs["min_strength"] == "MODERATE"
    assert prefs["strong_only"] is False

    patched = (await client.patch(
        "/api/v1/notifications/preferences",
        json={"strong_only": True, "bearish_alerts": False},
        headers=h,
    )).json()["data"]
    assert patched["strong_only"] is True and patched["bearish_alerts"] is False
    assert patched["bullish_alerts"] is True  # untouched fields persist


async def test_deactivate_token(client):
    h, token = await _mk_user_with_device(client)
    off = await client.delete(f"/api/v1/notifications/tokens?fcm_token={token}", headers=h)
    assert off.json()["data"]["deactivated"] is True
    overview = (await client.get("/api/v1/notifications", headers=h)).json()["data"]
    assert all(t["is_active"] is False for t in overview["tokens"])


# ------------------------------------------------------------ dispatcher core

def _mk_signal_sync(db, direction: str = "BEARISH", strength: str = "STRONG"):
    raise RuntimeError("use async version")


async def _mk_signal(db, direction: str = "BEARISH", strength: str = "STRONG"):
    from datetime import datetime, timezone

    from app.models import Signal, SignalDirection, SignalStatus, SignalStrength, Timeframe

    inst = Instrument(symbol=f"S{uuid.uuid4().hex[:6].upper()}", exchange="NSE",
                      name="Signal Test Co", instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.flush()

    sig = Signal(
        instrument_id=inst.id,
        timeframe=Timeframe.H1,
        signal_type="BOF",
        direction=SignalDirection(direction),
        strength=SignalStrength(strength),
        status=SignalStatus.CONFIRMED,
        bof_level=100.5,
        confidence=0.7,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(sig)
    await db.commit()
    return sig, inst


async def _mk_pref_token(db, *, bullish=True, bearish=True, strong_only=False,
                         watchlist_only=False, min_strength="MODERATE",
                         token="dev-token"):
    """Direct DB user + prefs + device (bypasses API for matrix tests)."""
    from app.core.security import hash_password
    from app.models import User

    user = User(email=f"{uuid.uuid4().hex[:8]}@x.test",
                hashed_password=hash_password("whatever123"))
    db.add(user)
    await db.flush()
    db.add(NotificationPreference(
        user_id=user.id, push_enabled=True,
        bullish_alerts=bullish, bearish_alerts=bearish,
        strong_only=strong_only, watchlist_only=watchlist_only,
        min_strength=min_strength,
    ))
    db.add(NotificationToken(user_id=user.id, fcm_token=token))
    await db.commit()
    await db.flush()
    return user


async def test_dispatcher_respects_direction_toggles(client, db):
    sender = RecordingSender()
    dispatcher = NotificationDispatcher(db, sender=sender)  # type: ignore[arg-type]

    await _mk_pref_token(db, bearish=False)                 # wants bullish only
    sig, inst = await _mk_signal(db, direction="BEARISH")
    sent = await dispatcher.notify_new_signal(sig, inst)
    assert sent == 0 and sender.sent == []

    sig2, inst2 = await _mk_signal(db, direction="BULLISH")
    sent = await dispatcher.notify_new_signal(sig2, inst2)
    assert sent >= 1 and len(sender.sent) == 1
    body_tokens, msg = sender.sent[0]
    assert msg.data["type"] == "bof_signal" and "symbol" in msg.data


async def test_strong_only_filter_blocks_weak(client, db):
    sender = RecordingSender()
    dispatcher = NotificationDispatcher(db, sender=sender)  # type: ignore[arg-type]

    await _mk_pref_token(db, strong_only=True)
    weak_sig, weak_inst = await _mk_signal(db, strength="WEAK")
    assert await dispatcher.notify_new_signal(weak_sig, weak_inst) == 0

    strong_sig, strong_inst = await _mk_signal(db, strength="VERY_STRONG")
    assert await dispatcher.notify_new_signal(strong_sig, strong_inst) >= 1


async def test_watchlist_only_requires_alert_enabled_item(client, db):
    sender = RecordingSender()
    dispatcher = NotificationDispatcher(db, sender=sender)  # type: ignore[arg-type]

    user = await _mk_pref_token(db, watchlist_only=True)
    sig, inst = await _mk_signal(db)

    # no watchlist â†’ nothing
    assert await dispatcher.notify_new_signal(sig, inst) == 0

    # watchlist item without alert flag → still nothing
    from sqlalchemy import select as sa_select

    from app.models import Watchlist, WatchlistItem

    wl = Watchlist(user_id=user.id, name="alerts")
    db.add(wl)
    await db.flush()
    db.add(WatchlistItem(watchlist_id=wl.id, instrument_id=inst.id, alert_enabled=False))
    await db.commit()
    assert await dispatcher.notify_new_signal(sig, inst) == 0

    # alert enabled → delivered
    item = (
        (await db.execute(sa_select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id)))
        .scalars().one()
    )
    item.alert_enabled = True
    await db.commit()
    assert await dispatcher.notify_new_signal(sig, inst) >= 1


async def test_log_sender_counts():
    s = LogSender()
    n = await s.send(["t1", "t2"], PushMessage(title="a", body="b", data={}))
    assert n == 2



