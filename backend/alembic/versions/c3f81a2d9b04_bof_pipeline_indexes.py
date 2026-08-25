"""bof pipeline indexes

Revision ID: c3f81a2d9b04
Revises: e8d5b433f6b3
Create Date: 2026-08-25

Adds the BOF-engine idempotency guarantees:
    - UNIQUE (instrument_id, timeframe, detected_at) on signals
      → engine replays can never duplicate a signal.
    - INDEX signal_events(signal_id, event_type)
      → fast "has this lifecycle event been recorded?" checks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f81a2d9b04'
down_revision: Union[str, None] = 'e8d5b433f6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('signals') as batch:
        batch.create_index(
            'uq_signals_instrument_tf_detected',
            ['instrument_id', 'timeframe', 'detected_at'],
            unique=True,
        )
    op.create_index(
        'ix_signal_events_signal_event',
        'signal_events',
        ['signal_id', 'event_type'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_signal_events_signal_event', table_name='signal_events')
    with op.batch_alter_table('signals') as batch:
        batch.drop_index('uq_signals_instrument_tf_detected')
