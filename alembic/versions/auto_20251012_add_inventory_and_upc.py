"""
Revision ID: auto_20251012_add_inventory_and_upc
Revises: auto_20251012_add_order_category
Create Date: 2025-10-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'auto_20251012_add_inventory_and_upc'
down_revision = 'auto_20251012_add_order_category'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = inspect(conn)
    if not insp.has_table('inventory'):
        op.create_table(
            'inventory',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('product', sa.String(length=200), nullable=False),
            sa.Column('upc', sa.String(length=50), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('vendor_id', sa.Integer(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
    # add upc column to line_item if missing
    if insp.has_table('line_item'):
        cols = [c['name'] for c in insp.get_columns('line_item')]
        if 'upc' not in cols:
            op.add_column('line_item', sa.Column('upc', sa.String(length=50), nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = inspect(conn)
    if insp.has_table('line_item'):
        cols = [c['name'] for c in insp.get_columns('line_item')]
        if 'upc' in cols:
            op.drop_column('line_item', 'upc')
    if insp.has_table('inventory'):
        op.drop_table('inventory')
