"""firebase user fields

Revision ID: e8d5b433f6b3
Revises: 42bcacb9869e
Create Date: 2026-08-24 22:34:08.170043

Adds Firebase/Google Sign-In support to ``users``:
    firebase_uid (unique), photo_url, auth_provider, last_login_at,
    and makes hashed_password nullable (Google users have no password).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8d5b433f6b3'
down_revision: Union[str, None] = '42bcacb9869e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill-safe default so tables with existing rows stay valid.
    op.add_column(
        'users',
        sa.Column('auth_provider', sa.Enum('PASSWORD', 'GOOGLE', name='authprovider',
                                           native_enum=False, length=12),
                  nullable=False, server_default='PASSWORD'),
    )
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('firebase_uid', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('photo_url', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column('hashed_password',
                              existing_type=sa.String(length=255),
                              nullable=True)
        batch_op.create_index(op.f('ix_users_firebase_uid'), ['firebase_uid'], unique=True)
    # Remove the backfill default once every row has a value.
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('auth_provider',
                              existing_type=sa.Enum('PASSWORD', 'GOOGLE', name='authprovider',
                                                    native_enum=False, length=12),
                              server_default=None)


def downgrade() -> None:
    # Refuse to destroy Google-only accounts implicitly.
    conn = op.get_bind()
    google_only = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE auth_provider = 'GOOGLE' AND hashed_password IS NULL")
    ).scalar_one()
    if google_only:
        raise RuntimeError(
            f"{google_only} Google-authenticated user(s) have no password; "
            "set or delete these accounts before downgrading."
        )

    op.drop_index(op.f('ix_users_firebase_uid'), table_name='users')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('last_login_at')
        batch_op.drop_column('photo_url')
        batch_op.drop_column('firebase_uid')
        batch_op.alter_column('hashed_password',
                              existing_type=sa.String(length=255),
                              nullable=False)
        batch_op.drop_column('auth_provider')
