"""official-data schema

Revision ID: 0001
"""
from alembic import op
from app.db.schema import metadata

revision = "0001"
down_revision = None

def upgrade():
    metadata.create_all(bind=op.get_bind())

def downgrade():
    metadata.drop_all(bind=op.get_bind())
