"""add skill_profile_json to users

Revision ID: 001
Revises:
Create Date: 2025-03-19

"""
from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("skill_profile_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "skill_profile_json")
