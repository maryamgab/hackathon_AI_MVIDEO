from normalization.normalization_utils import build_aliases, find_in_words
from normalization.dictionary.country_dictionary import COUNTRY_DICTIONARY
from normalization.morphology import normalize_phrase

COUNTRY_ALIASES = build_aliases(
    COUNTRY_DICTIONARY, normalize_phrase
)
MAX_COUNTRY_WORDS = max(
    (len(key) for key in COUNTRY_ALIASES), default=1
)


def normalize_country(value):
    cleaned = str(value).strip()
    return COUNTRY_ALIASES.get(
        normalize_phrase(cleaned), cleaned
    )


def find_countries_in_words(words):
    return find_in_words(
        words,
        COUNTRY_ALIASES,
        MAX_COUNTRY_WORDS,
        ignore_short_abbreviations=True,
    )