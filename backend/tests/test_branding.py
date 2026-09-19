from pathlib import Path

from PIL import Image

from app.branding import BrandingSettings, load_branding, public_branding, save_branding, store_logo


def test_branding_text_and_logos_persist(tmp_path: Path):
    value = BrandingSettings(
        application_title="Grid Vision",
        application_subtitle="Inspector",
        application_version="2.4",
        company_name="Sky Green Line",
        department="Technical Department",
        copyright_text="© 2026 Sky Green Line",
    )
    save_branding(tmp_path, value)
    assert load_branding(tmp_path) == value

    upload = tmp_path / "upload.jpg"
    Image.new("RGB", (320, 180), "green").save(upload)
    saved = store_logo(tmp_path, "company", upload)
    assert saved.suffix == ".png"
    with Image.open(saved) as image:
        assert image.format == "PNG"
        assert image.size == (320, 180)

    public = public_branding(tmp_path)
    assert public["application_title"] == "Grid Vision"
    assert public["company_logo_url"].startswith("/api/settings/assets/company-logo?v=")
    assert public["application_logo_url"] is None
