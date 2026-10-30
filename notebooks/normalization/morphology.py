import re
from functools import lru_cache

import pymorphy3

_MORPH = pymorphy3.MorphAnalyzer()

_TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_RUSSIAN_WORD_RE = re.compile(r"[а-я]+")


@lru_cache(maxsize=100_000)
def normalize_word(word: str) -> str:
    word = str(word).casefold().replace("ё", "е")

    if _RUSSIAN_WORD_RE.fullmatch(word):
        return _MORPH.parse(word)[0].normal_form.replace("ё", "е")

    return word


def normalize_phrase(text: str) -> tuple[str, ...]:
    text = str(text).casefold().replace("ё", "е")

    return tuple(
        normalize_word(word)
        for word in _TOKEN_RE.findall(text)
    )