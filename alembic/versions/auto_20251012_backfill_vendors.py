"""
Revision ID: backfill_vendors
Revises: 75cc7fe59818
Create Date: 2025-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.sql import table, column, select

revision = 'backfill_vendors'
down_revision = '75cc7fe59818'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    if not inspector.has_table('order'):
        # nothing to backfill
        return

    orders = connection.execute(sa.text('SELECT id, vendor FROM "order" WHERE vendor IS NOT NULL AND vendor != ""')).fetchall()
    # build a mapping of normalized_name -> canonical display name and ids
    groups = {}
    for o in orders:
        raw = o[1] or ''
        name = raw.strip()
        if not name:
            continue
        norm = name.lower()
        if norm not in groups:
            groups[norm] = {'canonical': name, 'rows': []}
        groups[norm]['rows'].append(o[0])

    # insert vendors for each canonical name and update orders to point to them
    for norm, data in groups.items():
        canonical = data['canonical']
        connection.execute(sa.text('INSERT INTO vendor (name) VALUES (:name)'), {'name': canonical})
        vendor_id = connection.execute(sa.text('SELECT last_insert_rowid()')).scalar()
        # update all orders that match this canonical group (case-insensitive)
        connection.execute(sa.text('UPDATE "order" SET vendor_id = :vid WHERE lower(trim(vendor)) = :norm'), {'vid': vendor_id, 'norm': norm})


def downgrade():
    # no-op: do not remove vendor rows on downgrade
    pass
