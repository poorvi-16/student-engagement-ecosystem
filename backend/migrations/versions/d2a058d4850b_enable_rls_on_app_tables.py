"""enable rls on app tables

Revision ID: d2a058d4850b
Revises: c146e108c0c5
Create Date: 2026-10-17 14:43:27.534250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = 'd2a058d4850b'
down_revision: Union[str, Sequence[str], None] = 'c146e108c0c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Supabase exposes the public schema via its REST API using the (public) anon key.
# RLS with no policies denies that path entirely; the backend connects as the table
# owner, which bypasses RLS. New tables must be added here (or in their own migration).
TABLES = ["user", "studentprofile", "event", "alembic_version"]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in TABLES:
        op.execute(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in TABLES:
        op.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY')
