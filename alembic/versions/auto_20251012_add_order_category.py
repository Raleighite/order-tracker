"""
Revision ID: auto_20251012_add_order_category
Revises: 75cc7fe59818
Create Date: 2025-10-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'auto_20251012_add_order_category'
down_revision = '75cc7fe59818'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    if not inspector.has_table('order'):
        # nothing to do
        return
    cols = [c['name'] for c in inspector.get_columns('order')]
    if 'category' not in cols:
        # add nullable category column; values can be populated later via backfill if desired
        op.add_column('order', sa.Column('category', sa.String(length=50), nullable=True))


def downgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    if inspector.has_table('order'):
        cols = [c['name'] for c in inspector.get_columns('order')]
        if 'category' in cols:
            op.drop_column('order', 'category')
