import re

from normalization.dictionary.measurement_dictionary import (
    NUMBER,
    WEIGHT_PATTERN,
    WEIGHT_UNIT_MAP,
    LENGTH_UNIT_MAP,
    ORDERED_DIMENSIONS_PATTERN,
    GENERIC_DIMENSIONS_PATTERN,
    NAMED_DIMENSION_PATTERN,
    TRIPLE_DIMENSIONS_PATTERN,
    UNIT_BEFORE_VALUE_PATTERN,
    NAME_MAP,
    NAMED_AREA_PATTERN,
    AREA_UNIT_BEFORE_VALUE_PATTERN,
    NAMED_VOLUME_PATTERN,
    VOLUME_UNIT_BEFORE_VALUE_PATTERN,
    NAMED_POWER_PATTERN,
    POWER_UNIT_BEFORE_VALUE_PATTERN,
)

from normalization.normalization_utils import normalize_key



# ============================================================
# ОБЩИЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def format_number(value):
    return value.replace(".", ",")


def normalize_length_unit(unit):
    return LENGTH_UNIT_MAP.get(unit.lower(), unit)


def normalize_weight_unit(unit):
    return WEIGHT_UNIT_MAP.get(unit.lower().rstrip("."), unit)


def add_unique(result, seen, name, value, unit):
    value = format_number(value)
    key = (name, value, unit)

    if key not in seen:
        seen.add(key)
        result.append((name, value, unit))


# ============================================================
# ИЗВЛЕЧЕНИЕ ВЕСА
# ============================================================

def extract_weights(text):

    if not text:
        return []


    text = re.sub(
        r"(?i)\b\d+\s*G\s*[/\\]\s*\d+\s*G\b",
        " ",
        text,
    )

    result = []
    seen = set()

    for match in WEIGHT_PATTERN.finditer(text):
        tail = text[match.end():]

        # Защита от ошибочного распознавания единиц площади
        # и некоторых обозначений длины.
        if re.match(
            r"\s*/\s*(?:кв\.?\s*м|м\s*[²2³3]|метр(?:а|ов)?)",
            tail,
            re.IGNORECASE,
        ):
            continue

        value = format_number(match.group("value"))
        unit = normalize_weight_unit(match.group("unit"))

        key = (value, unit)

        if key not in seen:
            seen.add(key)
            result.append((value, unit))

    return result


# ============================================================
# ИЗВЛЕЧЕНИЕ РАЗМЕРОВ, ПЛОЩАДИ, ОБЪЁМА И МОЩНОСТИ
# ============================================================

def extract_dimensions(text):
    if not text:
        return []

    result = []
    seen = set()
    occupied = []

    def add(name, value, unit):
        value = format_number(value)
        unit = normalize_length_unit(unit)

        key = (name, value, unit)

        if key not in seen:
            seen.add(key)
            result.append((name, value, unit))

    def overlaps(start, end):
        return any(
            start < occupied_end and end > occupied_start
            for occupied_start, occupied_end in occupied
        )

    # --------------------------------------------------------
    # 1. Размеры с указанным порядком Д × Ш × В
    # --------------------------------------------------------

    for match in ORDERED_DIMENSIONS_PATTERN.finditer(text):
        start, end = match.span()

        names = ("Длина", "Ширина", "Высота")

        for name, key in zip(names, ("a", "b", "c")):
            add(name, match.group(key), match.group("unit"))

        occupied.append((start, end))

    # --------------------------------------------------------
    # 2. Подписанные габариты: «Габариты 20 × 30 × 40 см»
    # --------------------------------------------------------

    for match in GENERIC_DIMENSIONS_PATTERN.finditer(text):
        start, end = match.span()

        if overlaps(start, end):
            continue

        value = "×".join(
            format_number(match.group(key))
            for key in ("a", "b", "c")
        )

        add("Габариты", value, match.group("unit"))
        occupied.append((start, end))

    # --------------------------------------------------------
    # 3. Размеры с названиями:
    # «длина 20 см», «шириной 30 см», «высота 40 см»
    # --------------------------------------------------------

    for match in NAMED_DIMENSION_PATTERN.finditer(text):
        start, end = match.span()

        if overlaps(start, end):
            continue

        raw_name = match.group("name").lower()
        name = NAME_MAP.get(raw_name)

        # Резервная обработка на случай отсутствия формы в NAME_MAP.
        if name is None:
            if raw_name.startswith(("длин", "глубин")):
                name = "Длина"
            elif raw_name.startswith("ширин"):
                name = "Ширина"
            elif raw_name.startswith("диаметр"):
                name = "Диаметр"
            elif raw_name.startswith("радиус"):
                name = "Радиус"
            else:
                name = "Высота"

        add(name, match.group("value"), match.group("unit"))
        occupied.append((start, end))

    # --------------------------------------------------------
    # 4. Три числа без подписи:
    # «20 × 30 × 40 см»
    # --------------------------------------------------------

    for match in TRIPLE_DIMENSIONS_PATTERN.finditer(text):
        start, end = match.span()

        if overlaps(start, end):
            continue

        value = "×".join(
            format_number(match.group(key))
            for key in ("a", "b", "c")
        )

        add("Габариты", value, match.group("unit"))
        occupied.append((start, end))

    # --------------------------------------------------------
    # 5. Единица перед значением:
    # «длина, см — 20»
    # --------------------------------------------------------

    for match in UNIT_BEFORE_VALUE_PATTERN.finditer(text):
        start, end = match.span()

        if overlaps(start, end):
            continue

        raw_name = match.group("label").lower()
        name = NAME_MAP.get(raw_name)

        if name is None:
            if raw_name.startswith(("длин", "глубин")):
                name = "Длина"
            elif raw_name.startswith("ширин"):
                name = "Ширина"
            elif raw_name.startswith("диаметр"):
                name = "Диаметр"
            elif raw_name.startswith("радиус"):
                name = "Радиус"
            else:
                name = "Высота"

        add(name, match.group("value"), match.group("unit"))
        occupied.append((start, end))

    # --------------------------------------------------------
    # 6. Площадь
    # --------------------------------------------------------

    for pattern in (
        NAMED_AREA_PATTERN,
        AREA_UNIT_BEFORE_VALUE_PATTERN,
    ):
        for match in pattern.finditer(text):
            start, end = match.span()

            if overlaps(start, end):
                continue

            value = format_number(match.group("value"))
            unit = match.group("unit").lower()

            add("Площадь", value, unit)
            occupied.append((start, end))

    # --------------------------------------------------------
    # 7. Объём
    # --------------------------------------------------------

    for pattern in (
        NAMED_VOLUME_PATTERN,
        VOLUME_UNIT_BEFORE_VALUE_PATTERN,
    ):
        for match in pattern.finditer(text):
            start, end = match.span()

            if overlaps(start, end):
                continue

            value = format_number(match.group("value"))
            unit = match.group("unit").lower()

            add("Объём", value, unit)
            occupied.append((start, end))

    # --------------------------------------------------------
    # 8. Мощность
    # --------------------------------------------------------

    for pattern in (
        NAMED_POWER_PATTERN,
        POWER_UNIT_BEFORE_VALUE_PATTERN,
    ):
        for match in pattern.finditer(text):
            start, end = match.span()

            if overlaps(start, end):
                continue

            value = format_number(match.group("value"))
            unit = match.group("unit").lower()

            add("Мощность", value, unit)
            occupied.append((start, end))

    return result


# ============================================================
# ОБЩЕЕ ИЗВЛЕЧЕНИЕ ИЗМЕРЯЕМЫХ ХАРАКТЕРИСТИК
# ============================================================

def extract_measurements(text):
    if not text:
        return []

    result = []
    seen = set()

    for value, unit in extract_weights(text):
        add_unique(result, seen, "Вес", value, unit)

    for name, value, unit in extract_dimensions(text):
        add_unique(result, seen, name, value, unit)
    result = combine_dimensions(result)
    return result


# ============================================================
# ДОБАВЛЕНИЕ ХАРАКТЕРИСТИК В FEATURES
# ============================================================

def add_measurement_attributes(features, measurements):
    for name, value, unit in measurements:
        target = next(
            (
                feature for feature in features
                if normalize_key(feature.get("@name", "")) == normalize_key(name)
                and normalize_key(feature.get("@unit", "")) == normalize_key(unit)
            ),
            None,
        )

        value_key = normalize_key(value)
        if target is None:
            features.append({
                "id": len(features) + 1,
                "@name": name,
                "#text": value,
                "@unit": unit,
                "confidence": 0.924,
                "_value_confidences": {value_key: 0.924},
            })
            continue

        existing = [
            item.strip()
            for item in re.split(r"\s*[;,]\s*|,\s+", target.get("#text", ""))
            if item.strip()
        ]
        value_confidences = target.get("_value_confidences")
        if not isinstance(value_confidences, dict):
            fallback = float(target.get("confidence", 0.998))
            value_confidences = {normalize_key(item): fallback for item in existing}
        else:
            value_confidences = {normalize_key(k): float(v) for k, v in value_confidences.items()}

        value_confidences[value_key] = max(float(value_confidences.get(value_key, 0.0)), 0.924)
        if value_key not in {normalize_key(item) for item in existing}:
            existing.append(value)
        target["#text"] = "; ".join(existing)
        target["_value_confidences"] = value_confidences

    return features



# ============================================================
# ОБЪЕДИНЕНИЕ ДЛИНЫ, ШИРИНЫ И ВЫСОТЫ В ГАБАРИТЫ
# ============================================================
def combine_dimensions(dimensions):
    result = list(dimensions)
    grouped = {}

    for name, value, unit in dimensions:
        if name == "Глубина":
            name = "Длина"

        if name in {"Длина", "Ширина", "Высота"}:
            grouped.setdefault(unit, {})[name] = value

    for unit, values in grouped.items():
        if all(
            name in values
            for name in ("Длина", "Ширина", "Высота")
        ):
            dimensions_value = (
                f"{values['Высота']}x"
                f"{values['Ширина']}x"
                f"{values['Длина']}"
            )

            item = (
                "Габаритные размеры (В*Ш*Д)",
                dimensions_value,
                unit,
            )

            if item not in result:
                result.append(item)

    return result
