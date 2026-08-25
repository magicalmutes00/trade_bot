"""Database-level tests: constraints, cascades, indexes exist."""

import uuid

import pytest
from sqlalchemy import inspect, select

from app.models import (
    Instrument,
    InstrumentType,
    User,
    Watchlist,
    WatchlistItem,
)


async def test_unique_symbol_exchange_constraint(db):
    db.add(Instrument(symbol="NIFTY", exchange="NSE", name="Nifty 50",
                      instrument_type=InstrumentType.INDEX))
    db.add(Instrument(symbol="NIFTY", exchange="NSE", name="Duplicate"))
    with pytest.raises(Exception):
        await db.commit()
    await db.rollback()


async def test_watchlist_cascade_deletes_items(db):
    user = User(email="u1@example.com", hashed_password="x" * 20)
    db.add(user)
    await db.flush()

    inst = Instrument(symbol="RELIANCE", exchange="NSE", name="Reliance Industries",
                      instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.flush()

    wl = Watchlist(user_id=user.id, name="Core")
    db.add(wl)
    await db.flush()
    db.add(WatchlistItem(watchlist_id=wl.id, instrument_id=inst.id))
    await db.commit()

    wl_id = wl.id
    item_count_before = len(
        (await db.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id == wl_id))).all()
    )
    assert item_count_before == 1

    await db.delete(wl)
    await db.commit()
    remaining = (
        await db.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id == wl_id))
    ).all()
    assert remaining == []


async def test_all_spec_tables_registered():
    from app.models import Base

    tables = set(Base.metadata.tables.keys())
    expected = {
        "users", "user_sessions", "password_reset_tokens", "sectors", "instruments",
        "market_data", "candles", "signals", "signal_events", "watchlists",
        "watchlist_items", "notification_tokens", "notification_preferences",
        "user_settings", "market_sessions", "system_events",
    }
    assert expected <= tables
