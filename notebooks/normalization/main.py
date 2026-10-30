import html
import json
import re
import pandas as pd
import time
import math
import unicodedata
from pathlib import Path

from config import INPUT_FILE, OUTPUT_FILE, PATH_TEXT
from normalization.morphology import normalize_phrase
from normalization.normalization_utils import normalize_key
from normalization.dictionary.attribute_aliases import ATTRIBUTE_ALIASES
from normalization.dictionary_normalization.country_normalization import (find_countries_in_words,normalize_country)
from normalization.dictionary_normalization.material_normalization import find_materials_in_words
from normalization.dictionary_normalization.color_normalization import (COLOR_ALIASES, extract_colors_from_words)
from normalization.dictionary_normalization.measurement_normalization import (extract_measurements,add_measurement_attributes, combine_dimensions)


#уверенность извлечения по источникам.
CONFIDENCE_SELLER = 0.998
CONFIDENCE_WARRANTY = 0.983
CONFIDENCE_COUNTRY = 0.978
CONFIDENCE_MATERIAL = 0.957
CONFIDENCE_COLOR = 0.957
CONFIDENCE_MEASUREMENT = 0.924


#для извлечения характеристик продавца из текста
NUMBER_PATTERN = re.compile(r"[\d\s.,+\-–—/×xX]+")
HEADER_PATTERN = re.compile(r"характеристик\w*(?:\s+[а-яёa-z0-9№-]+){0,5}\s*:", re.IGNORECASE)
SECTION_PATTERN = re.compile(r"^\s*(Комплектация|Упаковка|Инструкция|Гарантия|Описание|Примечание|Подключение)(?:\s+[^:.;!?]*)?\s*:", re.IGNORECASE)
FEATURE_PATTERN = re.compile(r"(?:^|[.;]\s*|•\s*)([^:;•\n]+?)\s*:\s*")

#для работы с unit
UNITS = sorted({
    "кВт·ч", "кВт/ч", "кВт", "МВт", "мА·ч", "А·ч", "мА", "А", "мкм", "мм", "см", "км", "м",
    "мг", "кг", "г", "мл", "л", "Вт", "мВ", "кВ", "В", "°C", "°F", "℃", "мм²", "см²", "м²",
    "км²", "мм³", "см³", "м³", "Гц", "кГц", "МГц", "ГГц", "дБ", "дюйм", "дюйма", "дюймов",
    "секунд", "секунда", "секунды", "с", "минут", "минута", "минуты", "мин", "часов", "часа", "час", "ч",
    "суток", "сутки", "дней", "день", "м/с", "км/ч", "об/мин", "шт.", "шт", "%",
}, key=len, reverse=True)
UNIT_PATTERNS = [(unit, re.compile(r"^(.*?)\s*" + re.escape(unit) + r"\s*$", re.IGNORECASE)) for unit in UNITS]


WARRANTY_VALUE = r"\d+(?:\s*(?:\+|[-–—])\s*\d+)?"
WARRANTY_UNIT = (
    r"лет|года|год|"
    r"дней|дня|день|суток|сутки|"
    r"месяцев|месяца|месяц|мес\.?|"
    r"недель|недели|неделя"
)
WARRANTY_PATTERN = re.compile(
    rf"""
    \b
    (?:
        срок\s+гарантии
        |гарантийный\s+срок
        |гаранти(?:я|и|ю|ей)
    )
    (?:\s+(?:производителя|изготовителя))?
    \s*[:\-–—]?\s*
    (?P<value>{WARRANTY_VALUE})
    (?:\s+(?P<unit>{WARRANTY_UNIT})\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


WARRANTY_REVERSED_PATTERN = re.compile(
    rf"""
    \b
    (?P<value>{WARRANTY_VALUE})
    \s+
    (?P<unit>{WARRANTY_UNIT})\b
    \s+гаранти(?:я|и|ю|ей)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

def extract_warranty(raw_description):
    if not raw_description:
        return None

    text = re.sub(r"\s+", " ", raw_description)

    match = WARRANTY_PATTERN.search(text)

    if not match:
        match = WARRANTY_REVERSED_PATTERN.search(text)

    if not match:
        return None

    value = re.sub(r"\s+", "", match.group("value"))
    unit = match.groupdict().get("unit")
    if not unit and not re.search(r"[+\-–—]", value):
        return None

    return {
        "@name": "Гарантия",
        "#text": value,
        "@unit": unit.lower().rstrip(".") if unit else "",
    }


def _sanitize_unicode(text, preserve_line_breaks=False):
    """Удаляет невидимые Unicode-форматирующие символы и управляющие коды."""
    text = unicodedata.normalize("NFC", text)
    cleaned = []
    for char in text:
        if preserve_line_breaks and char in "\r\n\t":
            cleaned.append("\n" if char in "\r\n" else " ")
            continue
        # Cf: zero-width/bidi/BOM/word-joiner; Cc/Cs: управляющие и суррогатные коды.
        # Отдельно удаляем soft hyphen, combining grapheme joiner и variation selectors.
        category = unicodedata.category(char)
        codepoint = ord(char)
        if (
            category in {"Cf", "Cs"}
            or (category == "Cc")
            or codepoint == 0x00AD
            or codepoint == 0x034F
            or 0xFE00 <= codepoint <= 0xFE0F
            or 0xE0100 <= codepoint <= 0xE01EF
        ):
            cleaned.append(" " if category == "Cc" else "")
        else:
            cleaned.append(char)
    return "".join(cleaned)


# Очистка HTML, эмодзи, невидимых Unicode-символов и лишних пробелов.
def clean_text(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""

    text = html.unescape(str(value))
    text = _sanitize_unicode(text)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\uFE0F\u200D]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*[-–—]+\s*$", "", text).strip()


# Преобразует HTML-описание в строки для разбора характеристик.
def html_to_lines(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return []
    text = html.unescape(str(value))
    text = _sanitize_unicode(text, preserve_line_breaks=True)
    text = re.sub(r"<br\s*/?>|</p\s*>|</div\s*>|</li\s*>|<li\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]*>", " ", text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


#приведение названии характеристик к общему названию из ATTRIBUTE_ALIASES
def normalize_attribute_name(name):
    cleaned = clean_text(name).strip(" :.-")
    return ATTRIBUTE_ALIASES.get(normalize_key(cleaned), cleaned)


# Разбивает строковое значение характеристики на отдельные значения.
def split_attribute_values(values):
    if isinstance(values, str):
        parts = re.split(r"\s*;\s*|,\s+", values.strip())
    else:
        parts = list(values or [])
    result = []
    seen = set()
    for value in parts:
        value = str(value).strip()
        key = normalize_key(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def make_value_confidences(values, confidence):
    """Уверенность каждого отдельного значения до объединения источников."""
    return {normalize_key(value): float(confidence) for value in split_attribute_values(values)}


def get_value_confidences(feature, values=None, fallback=None):
    """Возвращает карту значение -> уверенность, восстанавливая её для старых объектов."""
    values = split_attribute_values(feature.get("#text", "") if values is None else values)
    current = feature.get("_value_confidences")
    if isinstance(current, dict):
        result = {normalize_key(k): float(v) for k, v in current.items()}
    else:
        confidence = fallback
        if confidence is None:
            confidence = feature.get("confidence", CONFIDENCE_SELLER)
        result = make_value_confidences(values, confidence)
    for value in values:
        result.setdefault(normalize_key(value), float(fallback if fallback is not None else feature.get("confidence", CONFIDENCE_SELLER)))
    return result


def _color_family(value):
    """Возвращает базовый цвет для оттенка, например «нежно-розовый» -> «розовый»."""
    alias = COLOR_ALIASES.get(normalize_phrase(str(value)))
    if alias:
        canonical, _shade = alias
        return normalize_key(canonical)
    # Если цвет не распознан словарём, считаем его отдельной цветовой группой.
    return normalize_key(value)


def calculate_attribute_confidence(name, value_confidences):
    """Перемножает уверенности разных значений; оттенок и базовый цвет считает одной группой."""
    if not value_confidences:
        return 0.0

    if normalize_key(name) == normalize_key("Цвет"):
        # Для пары «нежно-розовый, розовый» берём максимум внутри группы розового,
        # но независимые цвета, например розовый и зелёный, перемножаем.
        confidence_by_family = {}
        for value, confidence in value_confidences.items():
            family = _color_family(value)
            confidence_by_family[family] = max(
                confidence_by_family.get(family, 0.0), float(confidence)
            )
        return math.prod(confidence_by_family.values())

    return math.prod(float(value) for value in value_confidences.values())


def merge_value_confidence_maps(target_map, incoming_map):
    """Для одинакового значения берём максимум, разные значения храним отдельно."""
    for value_key, confidence in incoming_map.items():
        target_map[value_key] = max(float(target_map.get(value_key, 0.0)), float(confidence))
    return target_map


def merge_confidence(target, incoming):
    """Совместимость со старым вызовом: объединяет скалярную уверенность максимумом."""
    target["confidence"] = round(max(float(target.get("confidence", 0.0)), float(incoming)), 6)


def add_text_attribute(features, name, values, separator=", ", confidence=CONFIDENCE_MATERIAL):
    if not values:
        return features
    values = split_attribute_values(values)
    if not values:
        return features

    target = next((x for x in features if normalize_key(x.get("@name", "")) == normalize_key(name)), None)
    if target is None:
        value_confidences = make_value_confidences(values, confidence)
        features.append({
            "@name": name,
            "#text": separator.join(values),
            "confidence": round(calculate_attribute_confidence(name, value_confidences), 6),
            "_value_confidences": value_confidences,
        })
        return features

    existing_values = split_attribute_values(target.get("#text", ""))
    value_confidences = get_value_confidences(target, existing_values)
    incoming_map = make_value_confidences(values, confidence)
    merge_value_confidence_maps(value_confidences, incoming_map)

    combined_values = []
    seen = set()
    for value in existing_values + values:
        key = normalize_key(value)
        if key and key not in seen:
            seen.add(key)
            combined_values.append(value)
    target["#text"] = separator.join(combined_values)
    target["_value_confidences"] = value_confidences
    target["confidence"] = round(calculate_attribute_confidence(name, value_confidences), 6)
    return features


def parse_seller_params(raw_params):
    """Преобразует поле param из Parquet в список характеристик."""
    if raw_params is None:
        return []
    if not isinstance(raw_params, (list, dict, str)):
        try:
            if pd.isna(raw_params):
                return []
        except (TypeError, ValueError):
            pass
    if isinstance(raw_params, str):
        raw_params = raw_params.strip()
        if not raw_params:
            return []
        try:
            raw_params = json.loads(raw_params)
        except (json.JSONDecodeError, TypeError):
            return []

    if isinstance(raw_params, dict):
        raw_params = raw_params.get("param", [raw_params])
    if isinstance(raw_params, dict):
        raw_params = [raw_params]
    if not isinstance(raw_params, list):
        return []

    result = []
    for item in raw_params:
        if not isinstance(item, dict):
            continue
        name = normalize_attribute_name(item.get("@name", item.get("name", "")))
        value = clean_text(item.get("#text", item.get("value", "")))
        unit = clean_text(item.get("@unit", item.get("unit", "")))
        if not name or not value:
            continue
        base_confidence = CONFIDENCE_SELLER
        if "гаранти" in normalize_key(name):
            base_confidence = CONFIDENCE_WARRANTY
            name = "Гарантия"
        value_confidences = make_value_confidences(value, base_confidence)
        confidence = calculate_attribute_confidence(name, value_confidences)
        feature = {
            "@name": name,
            "#text": value,
            "confidence": round(confidence, 6),
            "_value_confidences": value_confidences,
        }
        if unit:
            feature["@unit"] = unit
        result.append(feature)
    return result


# Нормализация списка характеристик и объединение повторяющихся полей.
def normalize_and_merge_attributes(features):
    merged = []
    lookup = {}
    for feature in features:
        name = normalize_attribute_name(feature.get("@name", ""))
        raw_value = clean_text(feature.get("#text", ""))
        unit = clean_text(feature.get("@unit", ""))
        fallback_confidence = float(feature.get("confidence", CONFIDENCE_SELLER))
        if not name or not raw_value:
            continue

        if "гаранти" in normalize_key(name):
            name = "Гарантия"
            fallback_confidence = CONFIDENCE_WARRANTY

        raw_parts = split_attribute_values(raw_value)
        source_map = get_value_confidences(feature, raw_parts, fallback_confidence)
        normalized_parts = []
        incoming_map = {}
        for part in raw_parts:
            normalized_part = normalize_country(part) if normalize_key(name) == "страна производства" else part
            normalized_part = clean_text(normalized_part)
            if not normalized_part:
                continue
            normalized_parts.append(normalized_part)
            part_confidence = source_map.get(normalize_key(part), fallback_confidence)
            part_key = normalize_key(normalized_part)
            incoming_map[part_key] = max(incoming_map.get(part_key, 0.0), float(part_confidence))

        if not normalized_parts:
            continue

        key = (normalize_key(name), normalize_key(unit))
        if key not in lookup:
            display_separator = ", " if normalize_key(name) in {
                normalize_key("Материал"), normalize_key("Цвет"), normalize_key("Страна производства")
            } else "; "
            unique_parts = []
            seen_parts = set()
            for part in normalized_parts:
                part_key = normalize_key(part)
                if part_key not in seen_parts:
                    seen_parts.add(part_key)
                    unique_parts.append(part)
            item = {
                "@name": name,
                "#text": display_separator.join(unique_parts),
                "confidence": round(calculate_attribute_confidence(name, incoming_map), 6),
                "_value_confidences": dict(incoming_map),
            }
            if unit:
                item["@unit"] = unit
            lookup[key] = item
            merged.append(item)
            continue

        item = lookup[key]
        existing_parts = split_attribute_values(item.get("#text", ""))
        combined_parts = list(existing_parts)
        seen_parts = {normalize_key(part) for part in existing_parts}
        for part in normalized_parts:
            part_key = normalize_key(part)
            if part_key not in seen_parts:
                seen_parts.add(part_key)
                combined_parts.append(part)
        merge_value_confidence_maps(item["_value_confidences"], incoming_map)
        display_separator = ", " if normalize_key(name) in {
            normalize_key("Материал"), normalize_key("Цвет"), normalize_key("Страна производства")
        } else "; "
        item["#text"] = display_separator.join(combined_parts)
        item["confidence"] = round(calculate_attribute_confidence(name, item["_value_confidences"]), 6)

    for item in merged:
        item.pop("id", None)
        item["confidence"] = round(float(item.get("confidence", CONFIDENCE_SELLER)), 6)
        item.pop("_value_confidences", None)
    return merged


#извлечение характеристик из описания товара
def parse_product_description(raw_description):
    lines = html_to_lines(raw_description)
    features = []
    in_features = False

    for line in lines:
        header = HEADER_PATTERN.search(line)
        if header and not in_features:
            in_features = True
            line = line[header.end():].strip()
            if not line:
                continue
        if not in_features:
            continue

        next_section = SECTION_PATTERN.search(line)
        if next_section:
            line = line[:next_section.start()].strip()
            in_features = False
        if not line:
            continue

        matches = list(FEATURE_PATTERN.finditer(line))
        for index, match in enumerate(matches):
            name = normalize_attribute_name(clean_text(match.group(1)).strip(" .;:-"))
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            value = clean_text(line[match.end():end]).strip(" .;:-")
            value, unit = extract_unit(value)
            if not name or not value:
                continue

            base_confidence = CONFIDENCE_SELLER
            if "гаранти" in normalize_key(name):
                name = "Гарантия"
                base_confidence = CONFIDENCE_WARRANTY
            value_confidences = make_value_confidences(value, base_confidence)
            feature = {
                "@name": name,
                "#text": value,
                "confidence": round(calculate_attribute_confidence(name, value_confidences), 6),
                "_value_confidences": value_confidences,
            }
            if unit:
                feature["@unit"] = unit
            features.append(feature)

    warranty = extract_warranty(clean_text(raw_description))

    if warranty:
        existing = next(
            (
                feature
                for feature in features
                if "гаранти" in normalize_key(
                    feature.get("@name", "")
                )
            ),
            None,
        )

        if existing is None:
            warranty["confidence"] = CONFIDENCE_WARRANTY
            features.append(warranty)

    return clean_text(raw_description), features


#для извлечения unit
def extract_unit(value):
    value = clean_text(value).strip()
    for unit, pattern in UNIT_PATTERNS:
        match = pattern.match(value)
        if not match or not re.search(r"\d", match.group(1)):
            continue
        number = match.group(1).strip()
        if NUMBER_PATTERN.fullmatch(number):
            return number, unit
    return value, None



#обработка карточки товара и нормализация характеристик
def process_product(sku_id, title, raw_description, raw_params=None):
    title = clean_text(title)
    description, features = parse_product_description(raw_description)
    features.extend(parse_seller_params(raw_params))
    full_text = f"{title} {description}"
    words = normalize_phrase(full_text)


    measurements = extract_measurements(full_text)
    measurements = combine_dimensions(measurements)

    measurements = [
        ("Длина" if name == "Глубина" else name, value, unit)
        for name, value, unit in measurements
    ]

    features = add_measurement_attributes(features, measurements)


    materials = find_materials_in_words(words)
    if materials:
        features = add_text_attribute(
            features,
            "Материал",
            materials,
            confidence=CONFIDENCE_MATERIAL,
        )

    colors = extract_colors_from_words(words)
    if colors:
        features = add_text_attribute(
            features,
            "Цвет",
            colors,
            confidence=CONFIDENCE_COLOR,
        )

    countries = find_countries_in_words(words)
    if countries:
        features = add_text_attribute(
            features,
            "Страна производства",
            countries,
            separator=", ",
            confidence=CONFIDENCE_COUNTRY,
        )


    features = normalize_and_merge_attributes(features)

    return {
        "@id": normalize_id(sku_id),
        "name": title,
        "description": description,
        "param": features
    }

#приводит id в нормальный вид
def normalize_id(value):
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return int(value) if re.fullmatch(r"\d+", value) else value


def main():
    try:
        dataframe = pd.read_parquet(INPUT_FILE)
    except FileNotFoundError:
        print(f"Ошибка: входной файл не найден: {INPUT_FILE}")
        return
    except PermissionError:
        print(f"Ошибка: нет прав на чтение файла: {INPUT_FILE}")
        return
    except (OSError, ValueError) as e:
        print(f"Ошибка чтения файла {INPUT_FILE}: {e}")
        return
    except Exception as e:
        print(f"Не удалось прочитать Parquet-файл: {type(e).__name__}: {e}")
        return


    required_columns = {"sku_id", "title", "description"}
    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        print(
            f"Ошибка: во входном файле отсутствуют столбцы: "
            f"{', '.join(sorted(missing_columns))}"
        )
        return


    try:
        input_columns = ["sku_id", "title", "description"]
        if "param" in dataframe.columns:
            input_columns.append("param")
        products = [
            process_product(*row)
            for row in dataframe[input_columns].itertuples(index=False, name=None)
        ]
    except Exception as e:
        print(
            f"Ошибка при обработке карточек товаров: "
            f"{type(e).__name__}: {e}"
        )
        return

    try:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(
                products,
                f,
                ensure_ascii=False,
                indent=2
            )
    except PermissionError:
        print(f"Ошибка: нет прав на запись файла: {OUTPUT_FILE}")
        return
    except (OSError, TypeError, ValueError) as e:
        print(f"Ошибка записи результата в {OUTPUT_FILE}: {e}")
        return


if __name__ == "__main__":
    main()