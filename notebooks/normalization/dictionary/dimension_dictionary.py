import re
LENGTH_UNIT_PATTERN = (
    r"миллиметр(?:а|ов)?|мм|"
    r"сантиметр(?:а|ов)?|см|"
    r"дециметр(?:а|ов)?|дм|"
    r"метр(?:а|ов)?|м|"
    r"millimeters?|millimeters?|mm|"
    r"centimeters?|cms?|"
    r"meters?|metres?|m"
)

NUMBER = r"\d+(?:[.,]\d+)?"

UNIT_MAP = {
    "миллиметр": "мм",
    "миллиметра": "мм",
    "миллиметров": "мм",
    "мм": "мм",
    "mm": "мм",
    "сантиметр": "см",
    "сантиметра": "см",
    "сантиметров": "см",
    "см": "см",
    "cm": "см",
    "cms": "см",
    "дециметр": "дм",
    "дециметра": "дм",
    "дециметров": "дм",
    "дм": "дм",
    "метр": "м",
    "метра": "м",
    "метров": "м",
    "м": "м",
    "m": "м",
    "meter": "м",
    "meters": "м",
    "metre": "м",
    "metres": "м",
}



NAMED_DIMENSION_PATTERN = re.compile(
    r"\b(?P<name>длин[аы]|ширин[аы]|высот[аы]|глубин[аы]|диаметр(?:а|ом)?|радиус(?:а|ом)?)\b"
    rf"(?:(?![.;!\n]).){{0,100}}?"
    rf"(?P<value>{NUMBER})\s*"
    rf"(?P<unit>{LENGTH_UNIT_PATTERN})\b",
    re.IGNORECASE,
)


# Размеры с обозначенным порядком Д × Ш × В
ORDERED_DIMENSIONS_PATTERN = re.compile(
    rf"(?P<order>д\s*[xх×*]\s*ш\s*[xх×*]\s*в|"
    rf"длина\s*[xх×*]\s*ширина\s*[xх×*]\s*высота)"
    rf"\s*[:=—-]?\s*"
    rf"(?P<a>{NUMBER})\s*[xх×*]\s*"
    rf"(?P<b>{NUMBER})\s*[xх×*]\s*"
    rf"(?P<c>{NUMBER})\s*"
    rf"(?P<unit>{LENGTH_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

# Общие габариты: размеры 20 × 30 × 40 см
GENERIC_DIMENSIONS_PATTERN = re.compile(
    rf"(?P<label>габариты|размеры|размер|габарит)"
    rf"\s*[:=—-]?\s*"
    rf"(?P<a>{NUMBER})\s*[xх×*]\s*"
    rf"(?P<b>{NUMBER})\s*[xх×*]\s*"
    rf"(?P<c>{NUMBER})\s*"
    rf"(?P<unit>{LENGTH_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

# Три числа с единицей измерения, без подписи.
# Сохраняем как габариты, не назначая длину/ширину/высоту.
TRIPLE_DIMENSIONS_PATTERN = re.compile(
    rf"(?<![\w.,])"
    rf"(?P<a>{NUMBER})\s*[xх×*]\s*"
    rf"(?P<b>{NUMBER})\s*[xх×*]\s*"
    rf"(?P<c>{NUMBER})\s*"
    rf"(?P<unit>{LENGTH_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

NAME_MAP = {
    "длина": "Длина",
    "длины": "Длина",
    "ширина": "Ширина",
    "ширины": "Ширина",
    "высота": "Высота",
    "высоты": "Высота",
}


UNIT_BEFORE_VALUE_PATTERN = re.compile(
    rf"\b(?P<label>длин[аы]|ширин[аы]|высот[аы]|глубин[аы]|диаметр(?:а|ом)?|радиус(?:а|ом)?)\b"
    rf"[^.;!\n]{{0,60}}?"
    rf"\b(?P<unit>{LENGTH_UNIT_PATTERN})\b"
    rf"\s*\)?\s*[-:=—]\s*"
    rf"(?P<value>{NUMBER})(?![\d,])",
    re.IGNORECASE,
)

AREA_UNIT_PATTERN = (
    r"квадратн(?:ый|ого|ых|ые|ым|ыми)?\s*метр(?:а|ов)?|"
    r"кв\.?\s*м\.?|"
    r"м²|м2|"
    r"square\s*meters?|square\s*metres?|"
    r"sq\.?\s*m\.?"
)

NAMED_AREA_PATTERN = re.compile(
    rf"\bплощад[ьи]\b"
    rf"(?:(?![.;!\n]).){{0,100}}?"
    rf"(?P<value>{NUMBER})\s*"
    rf"(?P<unit>{AREA_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

AREA_UNIT_BEFORE_VALUE_PATTERN = re.compile(
    rf"\bплощад[ьи]\b"
    rf"[^.;!\n]{{0,60}}?"
    rf"(?P<unit>{AREA_UNIT_PATTERN})"
    rf"\s*[-:=—]\s*"
    rf"(?P<value>{NUMBER})(?![\d,])",
    re.IGNORECASE,
)

VOLUME_UNIT_PATTERN = (
    r"кубическ(?:ий|ого|их|ие|им|ими)?\s*метр(?:а|ов)?|"
    r"куб\.?\s*м\.?|"
    r"м³|м3|"
    r"литр(?:а|ов)?|л|"
    r"миллилитр(?:а|ов)?|мл|"
    r"l|ml|"
    r"cubic\s*meters?|cubic\s*metres?|"
    r"liters?|litres?|"
    r"milliliters?|millilitres?"
)

NAMED_VOLUME_PATTERN = re.compile(
    rf"\bобъ[её]м(?:а|ом)?\b"
    rf"(?:(?![.;!\n]).){{0,100}}?"
    rf"(?P<value>{NUMBER})\s*"
    rf"(?P<unit>{VOLUME_UNIT_PATTERN})(?!\w)",
    re.IGNORECASE,
)

VOLUME_UNIT_BEFORE_VALUE_PATTERN = re.compile(
    rf"\bобъ[её]м(?:а|ом)?\b"
    rf"[^.;!\n]{{0,60}}?"
    rf"\b(?P<unit>{VOLUME_UNIT_PATTERN})\b"
    rf"\s*\)?\s*[-:=—]\s*"
    rf"(?P<value>{NUMBER})(?![\d,])",
    re.IGNORECASE,
)

POWER_UNIT_PATTERN = (
    r"киловатт(?:а|ов)?|квт|кВт|"
    r"ватт(?:а|ов)?|вт|"
    r"kilowatts?|kw|"
    r"watts?|w"
)


NAMED_POWER_PATTERN = re.compile(
    rf"\bмощност[ьиью]\b"
    rf"(?:(?![.;!\n]).){{0,100}}?"
    rf"(?P<value>{NUMBER})\s*"
    rf"(?P<unit>{POWER_UNIT_PATTERN})(?!\w)",
    re.IGNORECASE,
)

POWER_UNIT_BEFORE_VALUE_PATTERN = re.compile(
    rf"\bмощност[ьиью]\b"
    rf"[^.;!\n]{{0,60}}?"
    rf"\b(?P<unit>{POWER_UNIT_PATTERN})\b"
    rf"\s*\)?\s*[-:=—]\s*"
    rf"(?P<value>{NUMBER})(?![\d,])",
    re.IGNORECASE,
)

