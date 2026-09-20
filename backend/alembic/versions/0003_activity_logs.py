"""Per-user audit events and browser visit summaries."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"

def upgrade():
    op.create_table("activity_events",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id"),nullable=False),
        sa.Column("occurred_at",sa.DateTime,nullable=False),
        sa.Column("action",sa.String(80),nullable=False),
        sa.Column("category",sa.String(30),nullable=False),
        sa.Column("summary",sa.String(300),nullable=False),
        sa.Column("outcome",sa.String(20),nullable=False),
        sa.Column("source",sa.String(20),nullable=False),
        sa.Column("image_id",sa.Integer),sa.Column("image_name",sa.String(255)),sa.Column("inspection_id",sa.Integer))
    for column in ("user_id","occurred_at","action","image_id"):
        op.create_index(f"ix_activity_events_{column}","activity_events",[column])
    op.create_table("activity_visits",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id"),nullable=False),
        sa.Column("session_hash",sa.String(64),nullable=False),
        sa.Column("started_at",sa.DateTime,nullable=False),sa.Column("last_seen_at",sa.DateTime,nullable=False),
        sa.Column("ended_at",sa.DateTime),sa.Column("end_reason",sa.String(60)),
        sa.Column("foreground_seconds",sa.Float,nullable=False),sa.Column("visible",sa.Boolean,nullable=False),
        sa.Column("page",sa.String(40),nullable=False),sa.Column("image_id",sa.Integer),sa.Column("sequence",sa.Integer,nullable=False))
    for column in ("user_id","session_hash","started_at"):
        op.create_index(f"ix_activity_visits_{column}","activity_visits",[column])

def downgrade():
    op.drop_table("activity_visits")
    op.drop_table("activity_events")
