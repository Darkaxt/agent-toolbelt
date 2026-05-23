import json
from io import BytesIO

import pytest

from amazon_intent_cli import cli


class FakeService:
    def __init__(self) -> None:
        self.calls = []

    def search(
        self,
        base: str,
        marketplace: str,
        refresh_intent: bool,
        mode: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        pages: int = 1,
    ) -> dict:
        self.calls.append(
            ("search", base, marketplace, refresh_intent, mode, brand, model, min_price, max_price, pages)
        )
        return {
            "command": "search",
            "query": base,
            "marketplace": marketplace,
            "mode": mode,
            "filters": {
                "base": base,
                "brand": brand,
                "model": model,
                "min_price": min_price,
                "max_price": max_price,
            },
            "pagination": {
                "pages_requested": pages,
                "pages_fetched": 1,
                "partial": False,
                "stopped_reason": None,
            },
            "intent": None if mode == "plain" else {"canonical_brand": brand or ""},
            "results": [],
        }

    def get(self, identifier: str, marketplace: str) -> dict:
        self.calls.append(("get", identifier, marketplace))
        return {"command": "get", "item": {"asin": "B0TEST"}} 

    def reviews(
        self,
        identifier: str,
        marketplace: str,
        limit: int | None,
        *,
        portal: str = "retail",
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        isolated: bool = False,
    ) -> dict:
        self.calls.append(
            ("reviews", identifier, marketplace, limit, portal, user_data_dir, profile_directory, isolated)
        )
        return {
            "command": "reviews",
            "marketplace": marketplace,
            "portal": portal,
            "asin": "B0TEST",
            "limit": limit,
            "item": {"asin": "B0TEST", "title": "LG OLED65C5ELB"},
            "review_insights": {"summary": "Customers like the image quality."},
            "reviews_source": "product_reviews",
            "deep_reviews_available": True,
            "session_source": "managed_profile",
            "final_url": "https://www.amazon.de/-/en/product-reviews/B0TEST",
            "fallback_reason": None,
            "pagination": {"pages_fetched": 1, "stopped_reason": None},
            "reviews": [{"author": "Dynamite", "title": "Great", "body": "Excellent TV"}],
        }

    def compare(self, identifiers: list[str], marketplace: str) -> dict:
        self.calls.append(("compare", identifiers, marketplace))
        return {"command": "compare", "items": [{"asin": value} for value in identifiers]}

    def offers(
        self,
        identifier: str,
        marketplace: str,
        *,
        portal: str = "retail",
        marketplaces: list[str] | None = None,
        include_shipping: bool = True,
        vat_mode: str = "auto",
    ) -> dict:
        self.calls.append(("offers", identifier, marketplace, portal, marketplaces, include_shipping, vat_mode))
        return {
            "command": "offers",
            "marketplace": marketplace,
            "portal": portal,
            "asin": "B0TEST",
            "include_shipping": include_shipping,
            "vat_mode": vat_mode,
            "requested_marketplaces": marketplaces or ["de", "fr", "es"],
            "best_offer": None,
            "trusted_best_offer": None,
            "raw_best_offer": None,
            "current_offer": None,
            "offers": [],
            "failures": [],
        }

    def address_inspect(
        self,
        *,
        portal: str = "retail",
        marketplaces: list[str] | None = None,
        reference_marketplace: str = "de",
    ) -> dict:
        self.calls.append(("address_inspect", portal, marketplaces, reference_marketplace))
        return {
            "command": "address.inspect",
            "portal": portal,
            "reference_marketplace": reference_marketplace,
            "requested_marketplaces": marketplaces or ["de", "fr", "es"],
            "address_consistency": {"status": "match"},
            "addresses": [],
        }

    def cart_add(
        self,
        identifier: str,
        marketplace: str,
        *,
        portal: str = "retail",
        quantity: int = 1,
        confirm_cart_add: bool = False,
    ) -> dict:
        self.calls.append(("cart_add", identifier, marketplace, portal, quantity, confirm_cart_add))
        return {
            "command": "cart.add",
            "status": "added",
            "asin": "B0TEST0001",
            "marketplace": marketplace,
            "portal": portal,
            "quantity": quantity,
            "title": "Pilexil Forte Max",
            "url": f"https://www.amazon.{marketplace}/dp/B0TEST0001",
            "final_url": f"https://www.amazon.{marketplace}/cart/smart-wagon",
            "cart_confirmation_detected": True,
            "warnings": [],
            "safety": {
                "checkout_performed": False,
                "buy_now_clicked": False,
            },
        }

    def cart_remove(
        self,
        identifier: str,
        marketplace: str,
        *,
        portal: str = "retail",
        quantity: int = 1,
        confirm_cart_remove: bool = False,
    ) -> dict:
        self.calls.append(("cart_remove", identifier, marketplace, portal, quantity, confirm_cart_remove))
        return {
            "command": "cart.remove",
            "status": "removed",
            "asin": "B0TEST0001",
            "marketplace": marketplace,
            "portal": portal,
            "quantity_requested": quantity,
            "quantity_removed": quantity,
            "quantity_before": quantity,
            "quantity_after": 0,
            "title": "Pilexil Forte Max",
            "url": f"https://www.amazon.{marketplace}/cart",
            "final_url": f"https://www.amazon.{marketplace}/cart",
            "cart_removal_detected": True,
            "warnings": [],
            "safety": {
                "checkout_performed": False,
                "buy_now_clicked": False,
            },
        }

    def cart_list(
        self,
        marketplace: str,
        *,
        portal: str = "retail",
    ) -> dict:
        self.calls.append(("cart_list", marketplace, portal))
        return {
            "command": "cart.list",
            "marketplace": marketplace,
            "portal": portal,
            "url": f"https://www.amazon.{marketplace}/-/en/gp/cart/view.html",
            "final_url": f"https://www.amazon.{marketplace}/-/en/gp/cart/view.html",
            "session_key": f"{marketplace}:{portal}",
            "status": "ok",
            "items": [{"asin": "B0TEST0001", "title": "Pilexil Forte Max", "quantity": 2}],
            "item_count": 1,
            "warnings": [],
            "action_timing_ms": 12,
            "wait_strategy": "targeted",
            "safety": {
                "checkout_performed": False,
                "buy_now_clicked": False,
                "cart_mutation_performed": False,
            },
        }

    def bootstrap_session(
        self,
        marketplace: str,
        browser_executable: str | None,
        headless: bool,
        url: str | None,
        *,
        portal: str = "retail",
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        isolated: bool = False,
        login_timeout_sec: int = 300,
        manual_confirm: bool = False,
    ) -> dict:
        self.calls.append(
            (
                "bootstrap_session",
                marketplace,
                portal,
                browser_executable,
                headless,
                url,
                user_data_dir,
                profile_directory,
                isolated,
                login_timeout_sec,
                manual_confirm,
            )
        )
        return {
            "command": "session.bootstrap",
            "marketplace": marketplace,
            "portal": portal,
            "headless": headless,
            "session_source": "managed_profile",
            "session_key": f"{marketplace}:{portal}",
        }


def test_search_outputs_json_by_default(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["search", "LG C4", "--max-price", "560"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "search"
    assert payload["marketplace"] == "de"
    assert payload["mode"] == "plain"
    assert payload["filters"]["max_price"] == 560.0
    assert payload["pagination"]["pages_requested"] == 1
    assert service.calls[0][4:] == ("plain", None, None, None, 560.0, 1)


def test_search_with_brand_and_model_uses_exact_mode(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "search",
            "tv",
            "--brand",
            "LG",
            "--model",
            "C4",
            "--min-price",
            "100",
            "--max-price",
            "560",
            "--pages",
            "2",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "exact"
    assert payload["filters"] == {
        "base": "tv",
        "brand": "LG",
        "model": "C4",
        "min_price": 100.0,
        "max_price": 560.0,
    }
    assert payload["pagination"]["pages_requested"] == 2
    assert service.calls[0][4:] == ("exact", "LG", "C4", 100.0, 560.0, 2)


def test_similar_command_uses_similar_mode(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "similar",
            "tv",
            "--brand",
            "LG",
            "--model",
            "C4",
            "--marketplace",
            "es",
            "--max-price",
            "560",
            "--pages",
            "3",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "similar"
    assert payload["marketplace"] == "es"
    assert payload["pagination"]["pages_requested"] == 3
    assert service.calls[0][4:] == ("similar", "LG", "C4", None, 560.0, 3)


def test_search_rejects_model_without_brand(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["search", "tv", "--model", "C4"])


def test_search_rejects_invalid_price_bounds(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["search", "microwaves", "--min-price", "200", "--max-price", "100"])


@pytest.mark.parametrize("pages", ["0", "6"])
def test_search_rejects_invalid_page_bounds(monkeypatch, pages: str) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["search", "microwaves", "--pages", pages])


def test_compare_outputs_json(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["compare", "B0AAA", "B0BBB"])
    payload = json.loads(capsys.readouterr().out)

    assert [item["asin"] for item in payload["items"]] == ["B0AAA", "B0BBB"]


def test_inspect_identifier_accepts_asin_without_building_service(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: (_ for _ in ()).throw(AssertionError("service should not be built")))

    cli.main(["inspect-identifier", "b0test0001", "--marketplace", "fr"])
    payload = json.loads(capsys.readouterr().out)

    assert payload == {
        "command": "inspect-identifier",
        "input": "b0test0001",
        "identifier_type": "asin",
        "asin": "B0TEST0001",
        "requested_marketplace": "fr",
        "detected_marketplace": None,
        "marketplace": "fr",
        "marketplace_domain": "www.amazon.fr",
        "normalized_url": "https://www.amazon.fr/dp/B0TEST0001",
        "supported": True,
        "warnings": [],
    }


def test_inspect_identifier_detects_amazon_url_marketplace(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: (_ for _ in ()).throw(AssertionError("service should not be built")))

    cli.main(["inspect-identifier", "https://www.amazon.de/-/en/dp/b0test0001/ref=abc", "--marketplace", "fr"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["identifier_type"] == "amazon_url"
    assert payload["asin"] == "B0TEST0001"
    assert payload["requested_marketplace"] == "fr"
    assert payload["detected_marketplace"] == "de"
    assert payload["marketplace"] == "de"
    assert payload["marketplace_domain"] == "www.amazon.de"
    assert payload["normalized_url"] == "https://www.amazon.de/dp/B0TEST0001"
    assert payload["supported"] is True
    assert payload["warnings"] == []


def test_inspect_identifier_reports_unsupported_non_amazon_url(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: (_ for _ in ()).throw(AssertionError("service should not be built")))

    cli.main(["inspect-identifier", "https://example.com/dp/B0TEST0001"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["identifier_type"] == "url"
    assert payload["asin"] is None
    assert payload["marketplace"] == "de"
    assert payload["normalized_url"] is None
    assert payload["supported"] is False
    assert payload["warnings"] == ["Unsupported product URL domain: example.com"]


def test_offers_outputs_json_with_default_marketplaces(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["offers", "B0TEST0001", "--marketplace", "de"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "offers"
    assert payload["marketplace"] == "de"
    assert payload["portal"] == "retail"
    assert payload["include_shipping"] is True
    assert payload["vat_mode"] == "auto"
    assert service.calls[0] == ("offers", "B0TEST0001", "de", "retail", None, True, "auto")


def test_offers_accepts_marketplace_csv_portal_and_no_shipping(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "offers",
            "https://www.amazon.de/dp/B0TEST0001",
            "--marketplaces",
            "de,fr,es,uk",
            "--portal",
            "business",
            "--vat-mode",
            "excl",
            "--no-include-shipping",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["include_shipping"] is False
    assert payload["vat_mode"] == "excl"
    assert service.calls[0] == (
        "offers",
        "https://www.amazon.de/dp/B0TEST0001",
        "de",
        "business",
        ["de", "fr", "es", "uk"],
        False,
        "excl",
    )


def test_offers_rejects_invalid_vat_mode(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["offers", "B0TEST0001", "--vat-mode", "net"])


def test_offers_rejects_unknown_marketplace_in_csv(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["offers", "B0TEST0001", "--marketplaces", "de,xx"])


def test_address_inspect_outputs_json(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "address",
            "inspect",
            "--portal",
            "business",
            "--marketplaces",
            "de,es,fr,it",
            "--reference-marketplace",
            "de",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "address.inspect"
    assert payload["portal"] == "business"
    assert payload["requested_marketplaces"] == ["de", "es", "fr", "it"]
    assert service.calls[0] == ("address_inspect", "business", ["de", "es", "fr", "it"], "de")


def test_cart_add_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["cart", "add", "B0TEST0001", "--marketplace", "es", "--portal", "business"])


def test_cart_add_rejects_invalid_quantity(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(
            [
                "cart",
                "add",
                "B0TEST0001",
                "--marketplace",
                "es",
                "--quantity",
                "0",
                "--confirm-cart-add",
            ]
        )


def test_cart_add_outputs_json_after_explicit_confirmation(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "cart",
            "add",
            "B0TEST0001",
            "--marketplace",
            "es",
            "--portal",
            "business",
            "--quantity",
            "2",
            "--confirm-cart-add",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "cart.add"
    assert payload["status"] == "added"
    assert payload["safety"]["checkout_performed"] is False
    assert payload["safety"]["buy_now_clicked"] is False
    assert service.calls[0] == ("cart_add", "B0TEST0001", "es", "business", 2, True)


def test_cart_remove_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["cart", "remove", "B0TEST0001", "--marketplace", "es", "--portal", "business"])


def test_cart_remove_rejects_invalid_quantity(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(
            [
                "cart",
                "remove",
                "B0TEST0001",
                "--marketplace",
                "es",
                "--quantity",
                "0",
                "--confirm-cart-remove",
            ]
        )


def test_cart_remove_outputs_json_after_explicit_confirmation(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "cart",
            "remove",
            "B0TEST0001",
            "--marketplace",
            "es",
            "--portal",
            "business",
            "--quantity",
            "2",
            "--confirm-cart-remove",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "cart.remove"
    assert payload["status"] == "removed"
    assert payload["cart_removal_detected"] is True
    assert payload["safety"]["checkout_performed"] is False
    assert payload["safety"]["buy_now_clicked"] is False
    assert service.calls[0] == ("cart_remove", "B0TEST0001", "es", "business", 2, True)


def test_cart_list_outputs_json_without_confirmation(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["cart", "list", "--marketplace", "de", "--portal", "business"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "cart.list"
    assert payload["marketplace"] == "de"
    assert payload["portal"] == "business"
    assert payload["status"] == "ok"
    assert payload["item_count"] == 1
    assert payload["safety"]["cart_mutation_performed"] is False
    assert service.calls[0] == ("cart_list", "de", "business")


def test_reviews_outputs_json_without_default_limit(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["reviews", "https://www.amazon.de/dp/B0TEST0001"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "reviews"
    assert payload["limit"] is None
    assert payload["portal"] == "retail"
    assert service.calls[0] == (
        "reviews",
        "https://www.amazon.de/dp/B0TEST0001",
        "de",
        None,
        "retail",
        None,
        None,
        False,
    )


def test_reviews_accepts_explicit_limit(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["reviews", "B0TEST0001", "--limit", "20", "--marketplace", "fr"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["marketplace"] == "fr"
    assert payload["limit"] == 20
    assert service.calls[0] == ("reviews", "B0TEST0001", "fr", 20, "retail", None, None, False)


def test_reviews_accepts_retail_portal(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["reviews", "B0TEST0001", "--portal", "retail"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_source"] == "managed_profile"
    assert payload["final_url"] == "https://www.amazon.de/-/en/product-reviews/B0TEST"
    assert service.calls[0] == ("reviews", "B0TEST0001", "de", None, "retail", None, None, False)


def test_reviews_accepts_business_portal_for_fr(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["reviews", "B0TEST0001", "--marketplace", "fr", "--portal", "business", "--limit", "20"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["portal"] == "business"
    assert payload["limit"] == 20
    assert service.calls[0] == ("reviews", "B0TEST0001", "fr", 20, "business", None, None, False)


def test_reviews_rejects_unsupported_portal(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["reviews", "B0TEST0001", "--portal", "vendor"])


@pytest.mark.parametrize(
    "args",
    [
        ["reviews", "B0TEST0001", "--user-data-dir", r"C:\Helium\User Data"],
        ["reviews", "B0TEST0001", "--profile-directory", "Default"],
        ["reviews", "B0TEST0001", "--isolated"],
        ["session", "login", "--user-data-dir", r"C:\Helium\User Data"],
        ["session", "login", "--profile-directory", "Default"],
        ["session", "login", "--isolated"],
        ["session", "bootstrap", "--user-data-dir", r"C:\Helium\User Data"],
        ["session", "bootstrap", "--profile-directory", "Default"],
        ["session", "bootstrap", "--isolated"],
    ],
)
def test_deprecated_live_profile_flags_are_rejected(monkeypatch, args: list[str]) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(args)


@pytest.mark.parametrize("args", [["reviews", "--help"], ["session", "login", "--help"]])
def test_help_hides_deprecated_live_profile_flags(args: list[str], capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(args)
    output = capsys.readouterr().out

    assert "--user-data-dir" not in output
    assert "--profile-directory" not in output
    assert "--isolated" not in output


def test_reviews_rejects_invalid_limit(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["reviews", "B0TEST0001", "--limit", "0"])


def test_session_login_outputs_json(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["session", "login", "--browser-executable", r"C:\Chrome\chrome.exe"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "session.bootstrap"
    assert payload["session_source"] == "managed_profile"
    assert payload["session_key"] == "de:retail"
    assert service.calls[0][0] == "bootstrap_session"
    assert service.calls[0][3] == r"C:\Chrome\chrome.exe"
    assert service.calls[0][-2:] == (300, False)


def test_session_bootstrap_outputs_json_as_login_alias(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["session", "bootstrap", "--marketplace", "fr", "--portal", "retail"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "session.bootstrap"
    assert payload["marketplace"] == "fr"
    assert payload["session_key"] == "fr:retail"
    assert service.calls[0][0] == "bootstrap_session"
    assert service.calls[0][1] == "fr"
    assert service.calls[0][2] == "retail"
    assert service.calls[0][-2:] == (300, False)


def test_session_login_accepts_auto_detection_timeout_and_manual_fallback(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(
        [
            "session",
            "login",
            "--marketplace",
            "es",
            "--portal",
            "business",
            "--login-timeout-sec",
            "30",
            "--manual-confirm",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_key"] == "es:business"
    assert service.calls[0][1] == "es"
    assert service.calls[0][2] == "business"
    assert service.calls[0][-2:] == (30, True)


@pytest.mark.parametrize("timeout", ["0", "-1"])
def test_session_login_rejects_invalid_login_timeout(monkeypatch, timeout: str) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["session", "login", "--login-timeout-sec", timeout])


def test_session_login_accepts_business_portal_for_fr(monkeypatch, capsys) -> None:
    service = FakeService()
    monkeypatch.setattr(cli, "build_service", lambda: service)

    cli.main(["session", "login", "--marketplace", "fr", "--portal", "business"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_key"] == "fr:business"
    assert payload["portal"] == "business"
    assert service.calls[0][1] == "fr"
    assert service.calls[0][2] == "business"


def test_session_login_rejects_unsupported_portal(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda: FakeService())

    with pytest.raises(SystemExit):
        cli.main(["session", "login", "--portal", "vendor"])


def test_write_output_falls_back_to_utf8_buffer_when_console_encoding_rejects_text(monkeypatch) -> None:
    class EncodingFailStdout:
        def __init__(self) -> None:
            self.buffer = BytesIO()

        def write(self, text: str) -> int:
            raise UnicodeEncodeError("cp1252", text, 0, 1, "cannot encode")

    stdout = EncodingFailStdout()
    monkeypatch.setattr(cli.sys, "stdout", stdout)

    cli._write_output("alpha α")

    assert stdout.buffer.getvalue().decode("utf-8") == "alpha α\n"
