"""Accounts, revocable sessions, and private inspection ownership."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"

def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False),
        sa.Column("must_change_password", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False))
    op.create_table("user_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False))
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_table("login_attempts", sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer, nullable=False), sa.Column("window_start", sa.DateTime, nullable=False))
    with op.batch_alter_table("inspections") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer, nullable=True))
        batch.create_foreign_key("fk_inspections_owner", "users", ["owner_id"], ["id"])
        batch.create_index("ix_inspections_owner_id", ["owner_id"])
    with op.batch_alter_table("towers", naming_convention={"uq":"uq_%(table_name)s_%(column_0_name)s"}) as batch:
        batch.drop_constraint("uq_towers_tower_code", type_="unique")
        batch.add_column(sa.Column("owner_id", sa.Integer, nullable=True))
        batch.create_foreign_key("fk_towers_owner", "users", ["owner_id"], ["id"])
        batch.create_index("ix_towers_owner_id", ["owner_id"])
        batch.create_unique_constraint("uq_tower_owner_code", ["owner_id", "tower_code"])

def downgrade():
    raise RuntimeError("Restore the pre-migration backup to undo private workspace ownership.")
