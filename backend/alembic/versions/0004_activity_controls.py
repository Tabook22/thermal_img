"""Administrator control over per-user activity recording."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"

def upgrade():
    op.add_column("users", sa.Column("activity_logging_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("activity_logging_enabled")
