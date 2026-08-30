"""Management commands.

Usage (from /backend):
    python -m app.cli seed-admin --email admin@example.com --password <secret>
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import SessionFactory, engine
from app.models import User, UserRole


async def seed_admin(email: str | None, password: str | None) -> int:
    """Create (or promote) an admin user. Idempotent."""
    email = (email or settings.SEED_ADMIN_EMAIL or "").strip().lower()
    password = password or settings.SEED_ADMIN_PASSWORD or ""
    if not email or not password:
        print("error: provide --email/--password or SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD")
        return 2
    if len(password) < 8:
        print("error: admin password must be at least 8 characters")
        return 2
    try:
        from email_validator import validate_email

        validate_email(email, check_deliverability=False)
    except Exception as exc:
        print(f"error: invalid email ({exc})")
        return 2

    async with SessionFactory() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            existing.role = UserRole.ADMIN
            print(f"existing user promoted to admin: {email}")
        else:
            db.add(User(email=email, hashed_password=hash_password(password),
                        role=UserRole.ADMIN, display_name="Administrator"))
            print(f"admin created: {email}")
        await db.commit()
    return 0


async def swings_validate(
    symbol: str,
    timeframe: str = "D1",
    bars: int = 250,
    left: int = 3,
    right: int = 3,
) -> int:
    """Print the swing points, HH/HL/LH/LL sequence and trend for a symbol.

    Reads real stored candles (provider-sourced) and runs the pure swing
    analysis — for validating the structure module against historical charts
    before building patterns on top.
    """
    from sqlalchemy import func

    from app.engine.models import EngineCandle
    from app.engine.swings import analyse
    from app.models import Instrument, Timeframe

    tf_by_lower = {tf.value.lower(): tf.value for tf in Timeframe}
    resolved = tf_by_lower.get(timeframe.strip().lower())
    if resolved is None:
        print(f"error: unknown timeframe '{timeframe}' (use e.g. 15m, 1h, 1D, 1W)")
        return 2
    timeframe_enum = Timeframe(resolved)

    async with SessionFactory() as db:
        inst = (
            await db.execute(
                select(Instrument).where(
                    func.upper(Instrument.symbol) == symbol.strip().upper(),
                    Instrument.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if inst is None:
            print(f"error: no active instrument with symbol '{symbol}'")
            return 2

        from app.repositories.instrument_repository import InstrumentRepository

        rows = await InstrumentRepository(db).candles(
            instrument_id=inst.id, timeframe=timeframe_enum, limit=bars, before=None
        )
        # repository returns newest-first; engine wants chronological order
        candles = [
            EngineCandle(
                ts=c.ts,
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume or 0),
            )
            for c in reversed(rows)
        ]

    if len(candles) < right + 1:
        print(f"error: only {len(candles)} candles stored — need more for swing detection")
        return 2

    s = analyse(candles, left=left, right=right)
    print(f"\n{inst.symbol}  [{timeframe_enum.value}]  {len(candles)} bars  "
          f"swings={len(s.swings)}  trend={s.trend.value}")
    print("-" * 72)
    print(f"{'#':>3} {'when':<16} {'price':>9} {'side':<5} {'label':<4}")
    for sw in s.swings:
        when = sw.ts.strftime("%d %b %H:%M")
        print(f"{sw.index:>3} {when:<16} {sw.price:>9.2f} {sw.side.value:<5} "
              f"{(sw.label.value if sw.label else '-'):<4}")

    if s.highs:
        seq = " > ".join(
            f"{sw.price:.2f}({sw.label.value if sw.label else 'start'})" for sw in s.highs
        )
        print(f"swing highs: {seq}")
    if s.lows:
        seq = " > ".join(
            f"{sw.price:.2f}({sw.label.value if sw.label else 'start'})" for sw in s.lows
        )
        print(f"swing lows:  {seq}")
    return 0


async def patterns_validate(
    symbol: str,
    timeframe: str = "1D",
    bars: int = 250,
    left: int = 3,
    right: int = 3,
) -> int:
    """Print the detected chart patterns and their status for a symbol/timeframe.

    Reads real stored candles and runs the pattern detectors (built on the
    swing module) — for validating Stage 2 against historical charts.
    """
    from sqlalchemy import func

    from app.engine.models import EngineCandle
    from app.engine.patterns import detect_patterns
    from app.engine.swings import analyse
    from app.models import Instrument, Timeframe

    tf_by_lower = {tf.value.lower(): tf.value for tf in Timeframe}
    resolved = tf_by_lower.get(timeframe.strip().lower())
    if resolved is None:
        print(f"error: unknown timeframe '{timeframe}' (use e.g. 15m, 1h, 1D, 1W)")
        return 2
    timeframe_enum = Timeframe(resolved)

    async with SessionFactory() as db:
        inst = (
            await db.execute(
                select(Instrument).where(
                    func.upper(Instrument.symbol) == symbol.strip().upper(),
                    Instrument.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if inst is None:
            print(f"error: no active instrument with symbol '{symbol}'")
            return 2

        from app.repositories.instrument_repository import InstrumentRepository

        rows = await InstrumentRepository(db).candles(
            instrument_id=inst.id, timeframe=timeframe_enum, limit=bars, before=None
        )
        candles = [
            EngineCandle(
                ts=c.ts,
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume or 0),
            )
            for c in reversed(rows)
        ]

    if len(candles) < right + 1:
        print(f"error: only {len(candles)} candles stored — need more for pattern detection")
        return 2

    structure = analyse(candles, left=left, right=right)
    hits = detect_patterns(structure, candles)
    print(f"\n{inst.symbol}  [{timeframe_enum.value}]  {len(candles)} bars  "
          f"swings={len(structure.swings)}  trend={structure.trend.value}")
    print("-" * 72)
    if not hits:
        print("no chart patterns detected.")
        return 0

    for h in hits:
        t0, tv, t1 = h.swing_indices
        when = candles[h.confirm_index].ts.strftime("%d %b %H:%M")
        print(f"{h.name:<14} {h.direction.value:<8} {h.status.value:<9} "
              f"confirm@{when} conf={h.confidence:.2f}")
        print(f"    neckline={h.neckline_price:.2f} "
              f"swings=({t0},{tv},{t1}) idx")
    return 0


async def seed_instruments() -> int:
    """Idempotently seed sectors + instrument reference data (no prices)."""
    from sqlalchemy import select

    from app.core.seed_data import INSTRUMENTS, SECTORS
    from app.models import Instrument, InstrumentType, Sector

    async with SessionFactory() as db:
        sector_map: dict[str, object] = {}
        for name in SECTORS:
            existing = (
                await db.execute(select(Sector).where(Sector.name == name))
            ).scalar_one_or_none()
            if existing is None:
                existing = Sector(name=name)
                db.add(existing)
                await db.flush()
            sector_map[name] = existing

        created, skipped = 0, 0
        for symbol, exchange, name, itype, sector in INSTRUMENTS:
            exists = (
                await db.execute(
                    select(Instrument).where(
                        Instrument.symbol == symbol, Instrument.exchange == exchange
                    )
                )
            ).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue
            db.add(
                Instrument(
                    symbol=symbol,
                    exchange=exchange,
                    name=name,
                    instrument_type=InstrumentType(itype),
                    sector_id=sector_map[sector].id if sector else None,
                    currency="INR",
                )
            )
            created += 1
        await db.commit()
        print(f"instruments seeded: {created} created, {skipped} already present")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed-admin", help="create/promote an admin user")
    p_seed.add_argument("--email", default=None)
    p_seed.add_argument("--password", default=None)

    sub.add_parser("seed-instruments", help="seed sectors + instrument reference data")

    p_demo = sub.add_parser("backfill-demo", help="run the DEMO data + BOF pipeline")
    p_demo.add_argument("--days", type=int, default=45)
    p_demo.add_argument("--symbols", default=None, help="comma-separated filter, e.g. TCS,INFY")
    p_demo.add_argument("--skip-existing", action="store_true",
                        help="skip instruments whose M15 history is already complete")

    p_push = sub.add_parser("test-push", help="send a test push to a user's devices")
    p_push.add_argument("--email", required=True)
    p_push.add_argument("--symbol", default="TCS")

    p_swings = sub.add_parser("swings", help="validate swing/trend structure on real candles")
    p_swings.add_argument("--symbol", required=True)
    p_swings.add_argument("--timeframe", default="1D", help="15m | 1h | 1D | 1W (must be stored)")
    p_swings.add_argument("--bars", type=int, default=250)
    p_swings.add_argument("--left", type=int, default=3)
    p_swings.add_argument("--right", type=int, default=3)

    p_patterns = sub.add_parser("patterns", help="validate chart pattern detection on real candles")
    p_patterns.add_argument("--symbol", required=True)
    p_patterns.add_argument("--timeframe", default="1D", help="15m | 1h | 1D | 1W (must be stored)")
    p_patterns.add_argument("--bars", type=int, default=250)
    p_patterns.add_argument("--left", type=int, default=3)
    p_patterns.add_argument("--right", type=int, default=3)

    args = parser.parse_args()

    if args.command == "seed-admin":
        async def runner() -> int:
            try:
                return await seed_admin(args.email, args.password)
            finally:
                await engine.dispose()
        return asyncio.run(runner())

    if args.command == "seed-instruments":
        async def runner() -> int:
            try:
                return await seed_instruments()
            finally:
                await engine.dispose()
        return asyncio.run(runner())

    if args.command == "backfill-demo":
        async def runner() -> int:
            from app.workers.demo_pipeline import run_pipeline

            try:
                async with SessionFactory() as db:
                    symbols = set(args.symbols.split(",")) if args.symbols else None

                    def progress(symbol: str, done: int, totals: dict) -> None:
                        print(f"[{done}/{totals['instruments']}] {symbol}: "
                              f"candles={totals['candles']} "
                              f"signals+={totals['signals_created']} "
                              f"updated={totals['signals_updated']}", flush=True)

                    totals = await run_pipeline(db, symbols=symbols, days=args.days,
                                                progress=progress,
                                                skip_existing=args.skip_existing)
                    print("backfill-demo DONE:", totals, flush=True)
                    return 0
            finally:
                await engine.dispose()
        return asyncio.run(runner())

    if args.command == "test-push":
        async def runner() -> int:
            from sqlalchemy import select

            from app.services.notification_service import send_test_push

            try:
                async with SessionFactory() as db:
                    user = (
                        await db.execute(
                            select(User).where(User.email == args.email.strip().lower())
                        )
                    ).scalar_one_or_none()
                    if user is None:
                        print(f"error: no such user: {args.email}")
                        return 2
                    sent = await send_test_push(db, user.id, symbol=args.symbol)
                    await db.commit()
                    print(f"test push sent to {sent} device(s) for {args.email}")
                    return 0
            finally:
                await engine.dispose()
        return asyncio.run(runner())

    if args.command == "swings":
        async def runner() -> int:
            try:
                return await swings_validate(
                    args.symbol, timeframe=args.timeframe, bars=args.bars,
                    left=args.left, right=args.right,
                )
            finally:
                await engine.dispose()
        return asyncio.run(runner())

    if args.command == "patterns":
        async def runner() -> int:
            try:
                return await patterns_validate(
                    args.symbol, timeframe=args.timeframe, bars=args.bars,
                    left=args.left, right=args.right,
                )
            finally:
                await engine.dispose()
        return asyncio.run(runner())
    return 2


if __name__ == "__main__":
    sys.exit(main())

