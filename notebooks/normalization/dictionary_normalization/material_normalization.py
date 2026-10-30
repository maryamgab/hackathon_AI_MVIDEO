from normalization.normalization_utils import build_aliases, find_in_words
from normalization.dictionary.material_dictionary import MATERIAL_DICTIONARY
from normalization.morphology import normalize_phrase

MATERIAL_ALIASES = build_aliases(
    MATERIAL_DICTIONARY, normalize_phrase
)
MAX_MATERIAL_WORDS = max(
    (len(key) for key in MATERIAL_ALIASES), default=1
)

def find_materials_in_words(words):
    return find_in_words(
        words, MATERIAL_ALIASES, MAX_MATERIAL_WORDS
    )