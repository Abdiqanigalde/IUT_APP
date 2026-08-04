"""add profile_picture_url to user

Revision ID: 086974a635c6
Revises: d5cab2094753
Create Date: 2026-08-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '086974a635c6'
down_revision = 'd5cab2094753'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('profile_picture_url', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('user', 'profile_picture_url')
