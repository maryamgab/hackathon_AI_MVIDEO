import re
def build_aliases(dictionary, normalize_phrase):
    aliases = {}

    for canonical, variants in dictionary.items():
        for variant in [canonical, *variants]:
            key = normalize_phrase(variant)
            if key:
                aliases.setdefault(key, canonical)

    return aliases


def find_in_words(words, aliases, max_words, *, ignore_short_abbreviations=False):
    found = []
    occupied = set()

    for i in range(len(words)):
        if i in occupied:
            continue

        max_length = min(max_words, len(words) - i)

        for length in range(max_length, 0, -1):
            phrase = words[i:i + length]
            value = aliases.get(phrase)

            if value is None:
                continue

            if (
                ignore_short_abbreviations
                and len(phrase) == 1
                and len(phrase[0]) <= 2
                and phrase[0] not in {"сша", "оаэ"}
            ):
                continue

            if value not in found:
                found.append(value)

            occupied.update(range(i, i + length))
            break

    return found


#переводит названия атрибутов к единому виду (нижний регистр, й -> е, удаление лишних пробелов, знаков препинания, унификация разных тире)
def normalize_key(value):
    value = str(value).casefold().replace("ё", "е")
    value = re.sub(r"[‐‑‒–—−]", "-", value)
    value = re.sub(r"\s*[-/]\s*", lambda match: match.group(0).strip(), value)
    return re.sub(r"\s+", " ", value).strip(" :.")