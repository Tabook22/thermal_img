"""initial schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    op.create_table("towers", sa.Column("id", sa.Integer, primary_key=True), sa.Column("tower_code", sa.String(100), unique=True, nullable=False), sa.Column("circuit", sa.String(100)), sa.Column("verified_latitude", sa.Float), sa.Column("verified_longitude", sa.Float))
    op.create_table("inspections", sa.Column("id", sa.Integer, primary_key=True), sa.Column("tower_id", sa.Integer, sa.ForeignKey("towers.id"), nullable=False), sa.Column("phase", sa.String(30)), sa.Column("insulator_identifier", sa.String(100)), sa.Column("direction", sa.String(50)), sa.Column("capture_time", sa.DateTime), sa.Column("inspector_notes", sa.Text), sa.Column("ambient_conditions", sa.JSON), sa.Column("electrical_load", sa.String(100)), sa.Column("created_at", sa.DateTime, server_default=sa.func.now()))
    op.create_table("thermal_images", sa.Column("id", sa.Integer, primary_key=True), sa.Column("inspection_id", sa.Integer, sa.ForeignKey("inspections.id"), nullable=False), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("storage_name", sa.String(255), unique=True, nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("classification", sa.String(50), nullable=False), sa.Column("camera_model", sa.String(100)), sa.Column("camera_latitude", sa.Float), sa.Column("camera_longitude", sa.Float), sa.Column("metadata_json", sa.JSON), sa.Column("created_at", sa.DateTime, server_default=sa.func.now()))
    op.create_table("analysis_versions", sa.Column("id", sa.Integer, primary_key=True), sa.Column("image_id", sa.Integer, sa.ForeignKey("thermal_images.id"), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("sdk_version", sa.String(50)), sa.Column("matrix_path", sa.String(255)), sa.Column("width", sa.Integer), sa.Column("height", sa.Integer), sa.Column("parameters_json", sa.JSON), sa.Column("parameters_provenance", sa.JSON), sa.Column("stats_json", sa.JSON), sa.Column("warnings_json", sa.JSON), sa.Column("error", sa.Text), sa.Column("processed_at", sa.DateTime), sa.UniqueConstraint("image_id", "version"))
    op.create_table("regions", sa.Column("id", sa.Integer, primary_key=True), sa.Column("analysis_id", sa.Integer, sa.ForeignKey("analysis_versions.id"), nullable=False), sa.Column("name", sa.String(100), nullable=False), sa.Column("kind", sa.String(20), nullable=False), sa.Column("geometry_json", sa.JSON, nullable=False), sa.Column("stats_json", sa.JSON), sa.Column("is_reference", sa.Boolean, default=False))
    op.create_table("hotspot_observations", sa.Column("id", sa.Integer, primary_key=True), sa.Column("region_id", sa.Integer, sa.ForeignKey("regions.id"), nullable=False), sa.Column("threshold_c", sa.Float, nullable=False), sa.Column("minimum_area", sa.Integer, nullable=False), sa.Column("peak_c", sa.Float, nullable=False), sa.Column("pixel_area", sa.Integer, nullable=False), sa.Column("location_json", sa.JSON, nullable=False), sa.Column("outline_json", sa.JSON, nullable=False), sa.Column("reviewer_notes", sa.Text))
    op.create_table("reports", sa.Column("id", sa.Integer, primary_key=True), sa.Column("analysis_id", sa.Integer, sa.ForeignKey("analysis_versions.id"), nullable=False), sa.Column("storage_path", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime, server_default=sa.func.now()))

def downgrade():
    for table in ["reports", "hotspot_observations", "regions", "analysis_versions", "thermal_images", "inspections", "towers"]: op.drop_table(table)

