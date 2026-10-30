import json
import re
from pathlib import Path
from html import unescape
from openai import OpenAI
from rapidfuzz import fuzz, process
from config import BASE_URL, API_KEY, MODEL
from search.search import find_best_categories
from search.make_dicts import BrandModelExtractor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAG_DB_PATH = PROJECT_ROOT / "data" / "rag.sqlite"
brand_model_extractor = BrandModelExtractor(RAG_DB_PATH)
SCHEMA_PATH = PROJECT_ROOT / "data" / "ideal_attribute_schema.json"
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

with SCHEMA_PATH.open(encoding="utf-8") as f:
    IDEAL_SCHEMA = json.load(f)

CATEGORIES = IDEAL_SCHEMA["categories"]

CATEGORY_NAMES = [
    str(c.get("category", c.get("category_name", "")))
    for c in CATEGORIES
]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def clean_text(value):
    """Remove HTML tags and normalize whitespace."""
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def ask_llm(system_prompt, user_payload):
    """Call an OpenAI-compatible chat completions endpoint."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0,
        max_tokens=4000,
    )

    content = response.choices[0].message.content or ""

    # Tolerate responses wrapped in Markdown fences.
    content = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$",
        "",
        content,
    )

    return json.loads(content)


def get_category_id(category):
    return category.get("category_id", category.get("categoryId"))


def get_attribute_name(attribute):
    return (
        attribute.get("name")
        or attribute.get("canonical_name")
        or attribute.get("canonical")
        or attribute.get("attr")
    )


# --------------------------------------------------
# STEP 1. FIND CATEGORY CANDIDATES
# --------------------------------------------------

def find_category_candidates(product, limit=5):
    rag_results = find_best_categories(
        product.get("title", ""),
        product.get("description", ""),
        limit=limit,
    )

    schema_by_id = {
        str(get_category_id(c)): c
        for c in CATEGORIES
        if get_category_id(c) is not None
    }

    candidates = []

    for item in rag_results:
        cid = str(item["category_id"])
        schema_category = schema_by_id.get(cid)

        if schema_category is None:
            continue

        candidates.append({
            "category_id": get_category_id(schema_category),
            "category": schema_category.get(
                "category",
                schema_category.get("category_name", ""),
            ),
            "category_path": item["category_path"],
            "match_score": item["confidence"],
        })

    return candidates

# --------------------------------------------------
# STEP 2. ASK LLM TO SELECT CATEGORY
# --------------------------------------------------

def classify_category(product, candidates):
    if not candidates:
        return None

    # RAG уже ранжировал категории по похожести.
    best = candidates[0]
    best_score = float(best.get("match_score", 0))
    second_score = (
        float(candidates[1].get("match_score", 0))
        if len(candidates) > 1
        else 0.0
    )

    # Настраиваемые пороги уверенности.
    min_confidence = 0.70
    min_margin = 0.20

    confident = (
        best_score >= min_confidence
        and (
            len(candidates) == 1
            or best_score - second_score >= min_margin
        )
    )

    # Если RAG уверен, LLM не вызываем.
    if confident:
        best_id = str(best["category_id"])

        return next(
            (
                c for c in CATEGORIES
                if str(get_category_id(c)) == best_id
            ),
            None,
        )

    # Иначе просим LLM выбрать из найденных RAG вариантов.
    print(
        f"RAG недостаточно уверен: "
        f"top={best_score:.3f}, "
        f"margin={best_score - second_score:.3f}. "
        f"Передаём выбор LLM."
    )

    system_prompt = """
Ты классификатор товаров интернет-магазина.

Выбери наиболее подходящую категорию товара ТОЛЬКО
из переданного списка кандидатов.

Учитывай название, назначение, модель и описание товара.
Сравнивай полные пути категорий, а не только отдельные слова.
Не придумывай новые категории и ID.

Если ни одна категория не подходит, верни null.

Верни только JSON:
{
  "category_id": 123,
  "category": "Название категории"
}

Если подходящей категории нет:
{
  "category_id": null,
  "category": null
}
"""

    result = ask_llm(
        system_prompt,
        {
            "product": {
                "title": product.get("title", ""),
                "description": clean_text(
                    product.get("description", "")
                )[:2500],
            },
            "candidates": candidates,
        },
    )

    selected_id = result.get("category_id")

    # Не доверяем ID, которого нет среди кандидатов RAG.
    allowed_ids = {
        str(c["category_id"])
        for c in candidates
    }

    if (
        selected_id is None
        or str(selected_id) not in allowed_ids
    ):
        return None

    return next(
        (
            c for c in CATEGORIES
            if str(get_category_id(c)) == str(selected_id)
        ),
        None,
    )



# --------------------------------------------------
# STEP 3. EXTRACT CATEGORY ATTRIBUTES
# --------------------------------------------------

def extract_attributes(product, category):
    if category is None:
        return []

    # Exclude attributes explicitly marked as excluded.
    # Preserve core and optional candidates for manual review.
    attributes = [
        {
            "name": get_attribute_name(a),
            "source_fields": a.get("source_fields", []),
            "priority": a.get("priority"),
        }
        for a in category.get("attributes", [])
        if get_attribute_name(a)
        and a.get("priority") == "core"
    ]

    system_prompt = """
Ты система извлечения характеристик товаров.

Тебе переданы название, описание товара и список разрешённых
атрибутов из ideal_schema выбранной категории.

Правила:
1. Извлекай только значения, подтверждённые текстом товара.
2. Не придумывай значения и не используй общие знания о модели.
3. Используй только имена атрибутов из переданного списка.
4. Не добавляй атрибут, если значение неоднозначно или отсутствует.
5. Сохраняй числовые значения и единицы измерения корректно.
6. Если в тексте есть единица измерения, передавай её отдельно
   в поле unit. Если единицы нет, используй null.
7. Не путай возможности товара с подтверждёнными характеристиками.
8. Значения перечислений нормализуй осторожно, не меняя смысл.
9. Если несколько фрагментов текста описывают один атрибут,
   верни одно наиболее точное значение.
10. Не возвращай объяснения, confidence или другие поля.

Верни только JSON:
{
  "attributes": [
    {
      "name": "Название из списка",
      "value": "Извлечённое значение",
      "unit": "см"
    }
  ]
}

Если единицы нет:
{
  "name": "Цвет",
  "value": "чёрный",
}

Если значения не найдены:
{
  "attributes": []
}
"""

    result = ask_llm(
        system_prompt,
        {
            "product": {
                "sku_id": product["sku_id"],
                "title": product["title"],
                "description": clean_text(
                    product.get("description", "")
                ),
            },
            "category": {
                "category_id": get_category_id(category),
                "category": category.get(
                    "category",
                    category.get("category_name"),
                ),
            },
            "allowed_attributes": attributes,
        },
    )

    # Validate the response against the allowed schema.
    allowed_names = {
        str(a["name"]).casefold(): a["name"]
        for a in attributes
    }

    extracted = []
    seen = set()

    for item in result.get("attributes", []):
        raw_name = item.get("name")
        value = item.get("value")
        unit = item.get("unit")

        if not isinstance(raw_name, str):
            continue

        canonical_name = allowed_names.get(raw_name.casefold())

        if canonical_name is None:
            continue

        if not isinstance(value, (str, int, float)):
            continue

        value = str(value).strip()

        if not value:
            continue

        key = canonical_name.casefold()

        if key in seen:
            continue

        seen.add(key)

        param = {
            "@name": canonical_name,
            "#text": value,
        }

        if isinstance(unit, str) and unit.strip():
            param["@unit"] = unit.strip()

        extracted.append(param)

    return extracted


# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------
def process_product_with_llm(product): 
    candidates = find_category_candidates(product)
    category = classify_category(product, candidates)

    # ID категории берём из найденной категории (если она есть).
    # В словарях брендов ID хранятся как строки, поэтому приводим к str.
    category_id = get_category_id(category) if category else None
    category_id = str(category_id) if category_id is not None else None

    description = clean_text(product.get("description", ""))

    params = extract_attributes(product, category)

    return {
        "@id": product["sku_id"],
        "name": product["title"],
        "vendor": brand_model["brand"],
        "model": brand_model["model"],
        "description": description,
        "param": params,
    }