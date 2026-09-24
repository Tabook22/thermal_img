"""Private links to inspection evidence; no changes to existing images."""
from alembic import op
import sqlalchemy as sa
revision='0005'
down_revision='0004'
def upgrade():
    op.create_table('inspection_image_links',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('owner_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),
        sa.Column('image_id',sa.Integer,sa.ForeignKey('thermal_images.id'),nullable=False,unique=True),
        sa.Column('external_user_id',sa.Integer,nullable=False),sa.Column('external_image_id',sa.Integer,nullable=False),
        sa.Column('source_sha256',sa.String(64),nullable=False),sa.Column('ticket',sa.String(100),nullable=False),
        sa.Column('title',sa.String(500),nullable=False),sa.Column('return_path',sa.String(100),nullable=False),
        sa.Column('expires_at',sa.DateTime,nullable=False),
        sa.UniqueConstraint('owner_id','external_user_id','external_image_id','source_sha256',name='uq_inspection_image_link'))
    op.create_index('ix_inspection_image_links_owner_id','inspection_image_links',['owner_id'])
def downgrade():op.drop_table('inspection_image_links')
