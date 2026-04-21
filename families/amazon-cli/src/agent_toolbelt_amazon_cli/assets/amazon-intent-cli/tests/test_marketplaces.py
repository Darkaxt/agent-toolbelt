from amazon_intent_cli.marketplaces import DEFAULT_MARKETPLACE, PRIORITY_MARKETPLACES, get_marketplace


def test_marketplace_priority_starts_with_core_eu_sites() -> None:
    assert DEFAULT_MARKETPLACE == "de"
    assert PRIORITY_MARKETPLACES[:3] == ["de", "es", "fr"]


def test_get_marketplace_resolves_domain_and_language() -> None:
    marketplace = get_marketplace("fr")

    assert marketplace.code == "fr"
    assert marketplace.domain == "www.amazon.fr"
    assert marketplace.language == "fr-FR"


def test_get_marketplace_resolves_uk_for_eurosaver_offers() -> None:
    marketplace = get_marketplace("uk")

    assert marketplace.code == "uk"
    assert marketplace.domain == "www.amazon.co.uk"
    assert marketplace.currency == "GBP"


def test_get_marketplace_rejects_unknown_code() -> None:
    try:
        get_marketplace("us")
    except ValueError as exc:
        assert "Unsupported marketplace" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported marketplace")
