from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Marketplace:
    code: str
    domain: str
    language: str
    currency: str


DEFAULT_MARKETPLACE = "de"
PRIORITY_MARKETPLACES = ["de", "es", "fr", "it", "nl", "pl", "se", "be", "ie", "uk"]

SUPPORTED_MARKETPLACES: dict[str, Marketplace] = {
    "de": Marketplace("de", "www.amazon.de", "de-DE", "EUR"),
    "es": Marketplace("es", "www.amazon.es", "es-ES", "EUR"),
    "fr": Marketplace("fr", "www.amazon.fr", "fr-FR", "EUR"),
    "it": Marketplace("it", "www.amazon.it", "it-IT", "EUR"),
    "nl": Marketplace("nl", "www.amazon.nl", "nl-NL", "EUR"),
    "pl": Marketplace("pl", "www.amazon.pl", "pl-PL", "PLN"),
    "se": Marketplace("se", "www.amazon.se", "sv-SE", "SEK"),
    "be": Marketplace("be", "www.amazon.com.be", "fr-BE", "EUR"),
    "ie": Marketplace("ie", "www.amazon.ie", "en-IE", "EUR"),
    "uk": Marketplace("uk", "www.amazon.co.uk", "en-GB", "GBP"),
}


def get_marketplace(code: str) -> Marketplace:
    normalized = code.strip().lower()
    marketplace = SUPPORTED_MARKETPLACES.get(normalized)
    if marketplace is None:
        raise ValueError(f"Unsupported marketplace: {code}")
    return marketplace
