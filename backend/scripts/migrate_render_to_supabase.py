"""Migrate all data from the old Render Postgres into the Supabase Postgres.

The Render free-tier DB was suspended on ~2026-09-24 (30-day expiry). If it is
restored from the Render dashboard (upgrade within the grace window), this
script copies EVERY table — users, watchlists, signals, candles, sessions —
preserving primary keys so all foreign keys and login hashes keep working.

Usage (from backend/ with the venv active):

    python scripts/migrate_render_to_supabase.py --src "<old Render DATABASE_URL>"

The target defaults to DATABASE_URL from backend/.env (Supabase pooler) and
can be overridden with --dst. The target's data tables are truncated first, so
the script is idempotent — re-running after a partial copy is safe.

Source and target must both be on alembic head c3f81a2d9b04 (same schema).
"""

import argparse
import asyncio
import sys

import asyncpg

# Children are truncated before parents; tables are copied in reverse order.
TABLES = [
    "sectors",
    "instruments",
    "users",
    "user_settings",
    "notification_preferences",
    "notification_tokens",
    "market_data",
    "market_sessions",
    "candles",
    "signals",
    "signal_events",
    "watchlists",
    "watchlist_items",
    "password_reset_tokens",
    "user_sessions",
    "system_events",
]

_CHUNK = 1000


def _clean(url: str) -> str:
    """Strip query params — ssl is passed explicitly to asyncpg."""
    return url.split("?")[0]


async def _columns(conn, table: str) -> list[str]:
    rows = await conn.fetch(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name=$1 order by ordinal_position",
        table,
    )
    return [r["column_name"] for r in rows]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def copy_table(src, dst, table: str) -> int:
    cols = await _columns(src, table)
    collist = ", ".join(_quote_ident(c) for c in cols)
    rows = await src.fetch(f"select {collist} from {_quote_ident(table)}")

    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    insert = (
        f"insert into {_quote_ident(table)} ({collist}) values ({placeholders})"
    )
    for i in range(0, len(rows), _CHUNK):
        await dst.executemany(insert, [tuple(r) for r in rows[i : i + _CHUNK]])
    return len(rows)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="old Render DATABASE_URL")
    ap.add_argument("--dst", default=None, help="target URL (default: backend/.env DATABASE_URL)")
    args = ap.parse_args()

    dst_url = args.dst
    if not dst_url:
        from app.core.config import settings

        dst_url = settings.DATABASE_URL

    print("connecting to source…")
    src = await asyncpg.connect(_clean(args.src), ssl="require", timeout=30)
    print("connecting to target…")
    dst = await asyncpg.connect(_clean(dst_url), ssl="require", timeout=30)

    try:
        s_ver = await src.fetchval("select version_num from alembic_version")
        t_ver = await dst.fetchval("select version_num from alembic_version")
        print(f"schema versions: source={s_ver} target={t_ver}")
        if s_ver != t_ver:
            print("FATAL: schema versions differ — run alembic on both sides first")
            return 2

        print("truncating target data tables…")
        await dst.execute(
            "truncate table " + ", ".join(_quote_ident(t) for t in reversed(TABLES)) + " cascade"
        )

        print("copying…")
        copied: dict[str, int] = {}
        for table in TABLES:
            n = await copy_table(src, dst, table)
            copied[table] = n
            print(f"  {table:>26}: {n:>8} rows")

        print("verifying…")
        bad = 0
        for table in TABLES:
            s_n = await src.fetchval(f"select count(*) from {_quote_ident(table)}")
            t_n = await dst.fetchval(f"select count(*) from {_quote_ident(table)}")
            if s_n != t_n:
                bad += 1
                print(f"  MISMATCH {table}: source={s_n} target={t_n}")
        if bad:
            print(f"{bad} table(s) mismatched — re-run the script (it is idempotent)")
            return 1
        print("OK: all row counts match")
        return 0
    finally:
        await src.close()
        await dst.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
