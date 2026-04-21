from pathlib import Path


def test_manual_amazon_smoke_script_exists_and_stays_amazon_only() -> None:
    script = Path("scripts/smoke-amazon.ps1")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "amazon-cli search" in content
    assert "amazon-cli get" in content
    assert "amazon-cli reviews" in content
    assert "amazon-cli session login" in content
    assert "eurosaver" not in content.lower()


def test_manual_amazon_business_smoke_script_exists_and_uses_business_portal() -> None:
    script = Path("scripts/smoke-amazon-business.ps1")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "amazon-cli reviews" in content
    assert "--portal" in content
    assert "business" in content
    assert "eurosaver" not in content.lower()
