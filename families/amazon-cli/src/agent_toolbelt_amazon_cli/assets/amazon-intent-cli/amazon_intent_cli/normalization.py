from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

GENERIC_LABELS = {
    "brand_name": {
        "brand",
        "brand name",
        "marke",
        "marque",
        "marca",
    },
    "model_name": {
        "model name",
        "modellname",
        "nom du modele",
        "nombre del modelo",
    },
    "model_number": {
        "model number",
        "modellnummer",
        "numero du modele",
        "numero de modelo",
    },
    "manufacturer": {
        "manufacturer",
        "hersteller",
        "fabricant",
        "fabricante",
    },
}

MICROWAVE_LABELS = {
    "capacity_l": {"capacity", "kapazitat", "capacite", "capacidad"},
    "microwave_power_w": {"microwave power", "mikrowellenleistung", "puissance micro ondes", "potencia del microondas"},
    "grill_power_w": {"grill power", "grillleistung", "puissance du grill", "potencia del grill"},
    "power_levels": {"power levels", "leistungsstufen", "niveaux de puissance", "niveles de potencia"},
    "defrost": {"defrost", "auftaufunktion", "decongelation", "descongelacion"},
    "timer_minutes": {"timer", "minuterie", "temporizador"},
    "dimensions_cm": {"product dimensions", "produktabmessungen", "dimensions du produit", "dimensiones del producto"},
    "weight_kg": {"item weight", "artikelgewicht", "poids de l article", "peso del producto"},
    "turntable_cm": {
        "turntable diameter",
        "drehtellerdurchmesser",
        "diametre du plateau tournant",
        "diametro del plato giratorio",
    },
    "install_type": {"installation type", "installationstyp", "type d installation", "tipo de instalacion"},
    "control_type": {"control type", "steuerung", "type de commande", "tipo de control"},
    "color": {"color", "farbe", "couleur"},
}


BOOLEAN_TRUE = {
    "yes",
    "ja",
    "oui",
    "si",
    "sí",
    "true",
}

INSTALL_TYPE_VALUES = {
    "freistehend": "freestanding",
    "pose libre": "freestanding",
    "encimera": "freestanding",
    "countertop": "freestanding",
    "freestanding": "freestanding",
}

CONTROL_TYPE_VALUES = {
    "manuell": "manual",
    "manuel": "manual",
    "manual": "manual",
}

COLOR_VALUES = {
    "weiss": "white",
    "weiß": "white",
    "blanc": "white",
    "blanco": "white",
    "white": "white",
}


def _match_label(label: str, candidates: set[str]) -> bool:
    normalized = _normalize_text(label)
    return normalized in candidates


def _normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.casefold()).strip()


def _parse_float_from_text(value: str) -> float | None:
    match = re.search(r"([0-9][0-9\s\.,]*)", value)
    if not match:
        return None
    candidate = re.sub(r"\s+", "", match.group(1).strip())
    separators = [index for index, char in enumerate(candidate) if char in ".,"]  # noqa: C401
    decimal_separator: str | None = None
    decimal_index: int | None = None
    if separators:
        decimal_index = separators[-1]
        digits_after_separator = len(candidate) - decimal_index - 1
        if 0 < digits_after_separator <= 2:
            decimal_separator = candidate[decimal_index]
        elif len(separators) == 1 and digits_after_separator != 3:
            decimal_separator = candidate[decimal_index]

    normalized_chars: list[str] = []
    for index, char in enumerate(candidate):
        if char.isdigit():
            normalized_chars.append(char)
            continue
        if decimal_separator is not None and decimal_index == index and char == decimal_separator:
            normalized_chars.append(".")
    candidate = "".join(normalized_chars)
    if not candidate or candidate == ".":
        return None
    try:
        return float(Decimal(candidate))
    except InvalidOperation:
        return None


def _parse_int(value: str) -> int | None:
    parsed = _parse_float_from_text(value)
    if parsed is None:
        return None
    return int(parsed)


def _parse_bool(value: str) -> bool | None:
    normalized = _normalize_text(value)
    if normalized in {_normalize_text(item) for item in BOOLEAN_TRUE}:
        return True
    if normalized in {"no", "nein", "non", "false"}:
        return False
    return None


def _parse_dimensions_cm(value: str) -> dict[str, float] | None:
    matches = re.findall(r"[0-9]+(?:[.,][0-9]+)?", value)
    if len(matches) < 3:
        return None
    parsed = [_parse_float_from_text(match) for match in matches[:3]]
    if any(number is None for number in parsed):
        return None
    depth, width, height = parsed
    return {"depth": depth, "width": width, "height": height}


def _parse_enum(value: str, mapping: dict[str, str]) -> str | None:
    normalized = _normalize_text(value)
    return mapping.get(normalized)


def normalize_specs(specs: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for label, value in specs.items():
        for field_name, labels in GENERIC_LABELS.items():
            if _match_label(label, labels):
                normalized[field_name] = value.strip()
                break
        else:
            if _match_label(label, MICROWAVE_LABELS["capacity_l"]):
                parsed = _parse_int(value)
                if parsed is not None:
                    normalized["capacity_l"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["microwave_power_w"]):
                parsed = _parse_int(value)
                if parsed is not None:
                    normalized["microwave_power_w"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["grill_power_w"]):
                parsed = _parse_int(value)
                if parsed is not None:
                    normalized["grill_power_w"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["power_levels"]):
                parsed = _parse_int(value)
                if parsed is not None:
                    normalized["power_levels"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["defrost"]):
                parsed = _parse_bool(value)
                if parsed is not None:
                    normalized["defrost"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["timer_minutes"]):
                parsed = _parse_int(value)
                if parsed is not None:
                    normalized["timer_minutes"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["dimensions_cm"]):
                parsed = _parse_dimensions_cm(value)
                if parsed is not None:
                    normalized["dimensions_cm"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["weight_kg"]):
                parsed = _parse_float_from_text(value)
                if parsed is not None:
                    normalized["weight_kg"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["turntable_cm"]):
                parsed = _parse_float_from_text(value)
                if parsed is not None:
                    normalized["turntable_cm"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["install_type"]):
                parsed = _parse_enum(value, INSTALL_TYPE_VALUES)
                if parsed is not None:
                    normalized["install_type"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["control_type"]):
                parsed = _parse_enum(value, CONTROL_TYPE_VALUES)
                if parsed is not None:
                    normalized["control_type"] = parsed
            elif _match_label(label, MICROWAVE_LABELS["color"]):
                parsed = _parse_enum(value, COLOR_VALUES)
                if parsed is not None:
                    normalized["color"] = parsed

    normalized.setdefault("grill", "grill_power_w" in normalized)
    normalized.setdefault("convection", False)
    return normalized
