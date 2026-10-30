
from normalization.dictionary.color_dictionary import COLOR_DICTIONARY
from normalization.morphology import normalize_phrase


# Нормализованный вариант цвета -> (базовый цвет, оттенок)
COLOR_ALIASES = {}

for canonical, variants in COLOR_DICTIONARY.items():
    for variant in [canonical, *variants]:
        key = normalize_phrase(variant)
        if key:
            COLOR_ALIASES.setdefault(key, (canonical, variant))


MAX_COLOR_WORDS = max(
    (len(key) for key in COLOR_ALIASES), default=1
)


def extract_colors_from_words(words):
    found = []
    seen = set()
    occupied = set()

    for i in range(len(words)):
        if i in occupied:
            continue

        max_length = min(MAX_COLOR_WORDS, len(words) - i)

        for length in range(max_length, 0, -1):
            phrase = words[i:i + length]
            match = COLOR_ALIASES.get(phrase)

            if match is None:
                continue

            canonical, shade = match

            # Сначала добавляем найденный оттенок,
            # затем его базовый цвет.
            for color in (shade, canonical):
                normalized = normalize_phrase(color)

                if normalized not in seen:
                    seen.add(normalized)
                    found.append(color)

            occupied.update(range(i, i + length))
            break

    return found
