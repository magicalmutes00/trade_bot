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
    return 2


if __name__ == "__main__":
    sys.exit(main())

