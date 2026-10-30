# AI M.Video — извлечение, нормализация и обогащение карточек товаров

Проект обрабатывает карточки товаров: нормализует исходные характеристики, определяет категорию, находит бренд и модель, извлекает недостающие атрибуты и оценивает качество результата.

В проекте есть несколько самостоятельных контуров, которые важно не путать:

1. **Normalization** — приводит текст и характеристики карточки к единому виду.
2. **EDA** — анализирует исходный каталог, атрибуты и поисковые события; строит целевую схему атрибутов.
3. **RAG** — ищет похожие товары и категории по эмбеддингам. Для него отдельно собираются `catalog.sqlite` и `data/rag.sqlite`.
4. **Brand/model dictionaries** — таблицы брендов и моделей внутри `data/rag.sqlite`.
5. **Quality check** — использует таблицу `attr_values` в `data/rag.sqlite`, чтобы проверять значения атрибутов не только по тексту, но и по статистике каталога.
6. **FastAPI** — объединяет эти компоненты в единый сценарий обогащения товара.


---

## 1. Структура проекта

```text
project/
├── data/                            # файлы, которые используются в проекте
├── notebooks/
│   ├── app/                         # FastAPI, HTML и CSS
│   ├── eda/                         # EDA и построение схемы
│   ├── normalization/               # нормализация характеристик
│   ├── quality/                     # проверка качества и оценка extraction
│   ├── search/                      # построение каталога и RAG
│   ├── config.py
│   ├── main.py
│   ├── requirements.txt
│   └── extract_ideal_attributes.py
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── README.md
```

## 2. Требования

- Python 3.10+; Docker-образ использует Python 3.12.
- Зависимости из `notebooks/requirements.txt`.
- Исходные файлы проекта в `data/` и отдельный `notebooks/search/skus.pkl` для RAG-каталога.
- Доступ к LLM API для классификации и извлечения атрибутов.
- Доступ к Embeddings API для построения и поиска по векторам RAG.
- Для сборки и запуска в Docker — установленный Docker Compose.

Все команды в разделах ниже запускаются из корня репозитория, если явно не написано обратное.

## 3. Установка окружения

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r notebooks/requirements.txt
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r notebooks/requirements.txt
```

## 4. Настройка API

В проекте используются два обращения к API, добавьте свои API:

- **Chat/LLM** — настройки `BASE_URL`, `API_KEY`, `MODEL` из `notebooks/config.py`. 
- **Embeddings для RAG** — `notebooks/search/make_vectors.py`. 



## 5. Входные данные

### 5.1. Данные для EDA и основной схемы

Создайте `data/` в корне проекта и положите туда файлы:

| Файл | Для чего нужен |
|---|---|
| `skus.pkl` | исходный каталог для EDA (путь задан в `notebooks/config.py`) |
| `sku_desc.parquet` | тексты карточек; нормализация использует `sku_id`, `title`, `description`, опционально `param` |
| `query_clicks.parquet` | поисковые показы/клики; используется в EDA и приоритизации атрибутов |

Пути и имена задаются в `notebooks/config.py` и `notebooks/eda/config.py`. Сверяйте реальные названия столбцов с теми, которые проверяют скрипты.

### 5.2. Отдельный источник для RAG-каталога

Скрипт `notebooks/search/analyse_mvd.py` **не читает** `data/skus.pkl`. Он ожидает файл:

```text
notebooks/search/skus.pkl
```


```bash
mkdir -p notebooks/search
cp data/skus.pkl notebooks/search/skus.pkl
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force notebooks/search
Copy-Item data/skus.pkl notebooks/search/skus.pkl
```



## 6. Полный порядок подготовки проекта

Рекомендуемый порядок:

```text
Подготовить входные файлы и API-ключи
        |
        +--> Normalization
        |
        +--> EDA
                |
                +--> ideal_attribute_schema.json
                |
                +--> EDA search dictionaries
        |
        +--> RAG catalog: analyse_mvd.py
                |
                +--> catalog.sqlite + category_values.csv
                        |
                        +--> rag.sqlite / index_items
                        +--> item_vectors (Embeddings API)
                        +--> brand/model dictionaries
                        +--> attr_values (quality check)
        |
        +--> запуск FastAPI
```

Normalization и EDA не зависят друг от друга напрямую, поэтому их можно запускать независимо. Но для полного воспроизводимого запуска сначала подготовьте входные данные, затем выполните все этапы до запуска приложения.

### Шаг 1. Нормализация карточек

Из корня проекта:

```bash
cd notebooks
python -m normalization.main
```

Затем вернитесь в корень:

```bash
cd ..
```

- Вход: `data/sku_desc.parquet`.
- Выход: `data/normalized.json`.

Нормализация очищает текст, разбирает исходные параметры, унифицирует названия атрибутов, нормализует цвета/страны/материалы, приводит измерения и единицы к согласованному виду.

### Шаг 2. EDA

Из корня проекта:

```bash
python notebooks/eda/run_eda.py
```

Или из `notebooks/`:

```bash
cd notebooks
python -m eda.run_eda
```

`run_eda.py` запускает три скрипта по порядку:

1. `01_catalog.py` — собирает дерево категорий и мастер-каталог.
2. `02_attributes.py` — считает заполненность и разнообразие атрибутов, анализирует единицы и проблемы.
3. `03_search_priority.py` — оценивает связь заполненности атрибутов с поисковыми показами.

Основные результаты сохраняются в `data/reports/`, в том числе `catalog_master.parquet`, `category_tree.parquet`, `attribute_profile.parquet`, `attribute_issues.parquet`, `attribute_priority.parquet`.

Если `query_clicks.parquet` отсутствует, поисковая часть EDA может быть пропущена/неполной; для полноценной схемы предоставьте этот файл.

### Шаг 3. Построение целевой схемы атрибутов

Запускать после EDA:

```bash
cd notebooks
python eda/build_ideal_schema.py
```

Результат:

```text
data/ideal_attribute_schema.json
```

Скрипт использует исходные атрибуты, поисковые данные и мастер-каталог EDA. Схема содержит категории, список атрибутов, приоритеты и информацию о покрытии.

### Шаг 4. Словари поисковых значений EDA

После появления `ideal_attribute_schema.json`:

```bash
python eda/build_search_dictionaries.py
```

Результаты:

```text
data/search_dictionaries/
├── <category_id>.json
├── all_search_dictionaries.json
└── search_values_tmp.sqlite
```



## 7. Построение RAG и `data/rag.sqlite`

Это отдельная обязательная подготовка для работы определения категории и бренда/модели в приложении.

### Что хранится в `rag.sqlite`

Одна SQLite-база используется несколькими компонентами. В зависимости от выполненных этапов в ней появляются таблицы:

| Таблица | Кто создаёт | Для чего нужна |
|---|---|---|
| `index_items` | `make_vectors.py index` | компактный набор товаров и карточек категорий, которые индексируются |
| `item_vectors` | `make_vectors.py index` и `embed` | эмбеддинги строк из `index_items` |
| `spend` | `make_vectors.py index` и `embed` | учёт токенов Embeddings API по дням |
| `brands` | `make_dicts.py build` | нормализованные бренды и число товаров |
| `brand_aliases` | `make_dicts.py build` | варианты написания брендов и названия линеек |
| `brand_categories` | `make_dicts.py build` | связь брендов с категориями |
| `models` | `make_dicts.py build` | базовые модели по бренду и категории |
| `token_case` | `make_dicts.py build` | варианты регистра токенов моделей |
| `colors` | `make_dicts.py build` | словарь цветов для очистки названий моделей |
| `attr_values` | `quality.attr_check build` | частоты значений атрибутов по категориям для проверки качества |

### Шаг 7.1. Построить SQLite-каталог из PKL

Перейдите в `notebooks/`:

```bash
cd notebooks
python search/analyse_mvd.py
```

Скрипт читает `notebooks/search/skus.pkl` и создаёт:

```text
notebooks/search/catalog_analysis/
├── catalog.sqlite
├── fields.csv
├── categories.csv
├── parameters.csv
├── parameter_values.csv
├── category_parameters.csv
├── category_values.csv
├── product_field_values.csv
├── duplicate_sku.csv
└── products_without_category.csv
```

`catalog.sqlite` — промежуточный каталог, а не RAG-база. В нём есть таблицы `categories`, `products`, `product_categories`, `params`, `category_values`.

**Важно:** `analyse_mvd.py` завершится с ошибкой, если `catalog_analysis/catalog.sqlite` уже существует. Для полного пересоздания сначала сохраните нужные отчёты, затем переименуйте или удалите папку `notebooks/search/catalog_analysis/` и запустите скрипт заново.

### Шаг 7.2. Создать RAG-индекс (`index_items`)

Команда выполняется из `notebooks/`:

```bash
python search/make_vectors.py index \
  --db search/catalog_analysis/catalog.sqlite \
  --out ../data/rag.sqlite \
  --cap 200
```

Что делает `index`:

- читает товары и категории из `catalog.sqlite`;
- добавляет бренд к названию, если его там ещё нет;
- убирает одинаковые названия товаров внутри одной категории;
- оставляет не более `--cap` названий на категорию (по умолчанию 200);
- добавляет по одной текстовой «карточке» на категорию;
- создаёт `data/rag.sqlite` и таблицы `index_items`, `item_vectors`, `spend`.

На этом шаге в `item_vectors` ещё нет готовых эмбеддингов. Создан только набор строк, которые нужно векторизовать.

**Важно:** если в `rag.sqlite` уже есть `index_items`, команда `index` откажется перезаписывать индекс. Для полной пересборки удалите/переименуйте `data/rag.sqlite` (при этом придётся заново построить векторы и остальные таблицы).

### Шаг 7.3. Получить эмбеддинги (`item_vectors`)

Убедитесь, что задан `OPENAI_API_KEY`, затем сначала сделайте небольшой тест:

```bash
python search/make_vectors.py embed \
  --out ../data/rag.sqlite \
  --limit 1000
```

Если тест прошёл, запустите полную векторизацию:

```bash
python search/make_vectors.py embed --out ../data/rag.sqlite
```

Проверить результат:

```bash
python search/make_vectors.py stats --out ../data/rag.sqlite
```

Векторы сохраняются в `item_vectors` в формате float16. Обработанные строки сохраняются порциями; повторный запуск продолжает работу и обрабатывает только строки, для которых ещё нет вектора. По умолчанию задан дневной бюджет 95 ₽; при достижении лимита выполнение останавливается, после чего команду можно повторить позже. Учитывайте фактическую стоимость и лимиты вашего API.

### Шаг 7.4. Построить словари брендов и моделей

Эта команда читает товары из `catalog.sqlite` и записывает словари в **тот же** `data/rag.sqlite`:

```bash
python search/make_dicts.py build \
  --db search/catalog_analysis/catalog.sqlite \
  --out ../data/rag.sqlite
```

Будут созданы таблицы `brands`, `brand_aliases`, `brand_categories`, `models`, `token_case`, `colors`.

Если есть файл ручных соответствий брендов `brand_aliases_manual.csv`, его можно передать отдельно:

```bash
python search/make_dicts.py build \
  --db search/catalog_analysis/catalog.sqlite \
  --out ../data/rag.sqlite \
  --manual search/brand_aliases_manual.csv
```

Файл ручных соответствий необязателен: если его нет, скрипт строит словари на основе каталога.

**Этот шаг обязателен для текущего приложения:** `BrandModelExtractor` при импорте проверяет наличие `brand_aliases` в `rag.sqlite`. Без таблиц брендов/моделей запуск основного пайплайна завершится ошибкой.

### Шаг 7.5. Добавить справочник значений для Quality Check

`notebooks/main.py` создаёт `AttributeChecker(data/rag.sqlite)`. Если в базе есть таблица `attr_values`, проверка использует частоты значений и диапазоны чисел по категории. Если таблицы нет, остаётся только проверка по тексту товара.

Чтобы включить проверку по каталогу, используйте CSV, который создал `analyse_mvd.py`:

```bash
python -m quality.attr_check build \
  --values search/catalog_analysis/category_values.csv \
  --db ../data/rag.sqlite
```

Команда создаёт/пересоздаёт таблицу `attr_values` в уже существующей `rag.sqlite`, не удаляя остальные таблицы.

### Шаг 7.6. Проверить RAG

После полной векторизации можно оценить поиск категорий на товарах из базы:

```bash
python search/search.py eval --db ../data/rag.sqlite
```

Результат по умолчанию — `eval_report.csv` в текущей папке. Команда обращается к Embeddings API для тестовых запросов, поэтому `OPENAI_API_KEY` должен быть задан.

### Важное различие между тремя SQLite-файлами

| Файл | Как появляется | Назначение |
|---|---|---|
| `notebooks/search/catalog_analysis/catalog.sqlite` | `python search/analyse_mvd.py` | исходный SQLite-каталог из PKL; источник для RAG и quality CSV |
| `data/rag.sqlite` | `make_vectors.py index`, затем дополняется `embed`, `make_dicts.py build` и `quality.attr_check build` | рабочая база поиска категорий, брендов/моделей и проверки качества |
| `data/search_dictionaries/search_values_tmp.sqlite` | `python eda/build_search_dictionaries.py` | временная база для генерации JSON-словарей поисковых значений EDA; не используется вместо RAG |

## 8. Что происходит при обработке одного товара

Основной сценарий реализован в `notebooks/main.py`:

1. `normalization.main.process_product()` нормализует входные название, описание и исходные параметры.
2. `search.search.find_best_categories()` создаёт эмбеддинг запроса и ищет похожие строки в `rag.sqlite` (`index_items` + `item_vectors`).
3. `extract_ideal_attributes.py` сопоставляет найденные RAG-категории с `ideal_attribute_schema.json`.
4. Если RAG достаточно уверен (порог top score 0.70 и отрыв от второго кандидата 0.20), категория принимается без LLM. Иначе LLM выбирает только среди кандидатов RAG.
5. `BrandModelExtractor` ищет бренд и модель по словарям `brand_aliases`, `brands`, `models` и связанным таблицам в `rag.sqlite`.
6. Из `ideal_attribute_schema.json` выбираются отсутствующие атрибуты с приоритетом `core`; LLM извлекает только их.
7. `AttributeChecker` оценивает значения по исходному тексту, а при наличии `attr_values` — дополнительно по данным каталога.
8. В результате возвращаются нормализованные параметры, категория, бренд/модель и сводка `extraction_quality`.

RAG здесь — это retrieval по эмбеддингам для подбора кандидатов категорий. LLM не заменяет поиск: она вызывается для выбора между кандидатами, когда уверенности RAG недостаточно, и для извлечения недостающих характеристик.

## 9. Запуск приложения

Перед запуском приложения должны существовать:

- `data/ideal_attribute_schema.json`;
- `data/rag.sqlite` с таблицами `index_items`, `item_vectors` и словарями брендов/моделей;
- настроенный Chat/LLM API в `notebooks/config.py`;
- `OPENAI_API_KEY` в окружении процесса для Embeddings API (в том числе для эмбеддинга нового товара при поиске категории).

Из корня проекта:

```bash
uvicorn app.app:app --app-dir notebooks --host 0.0.0.0 --port 8000
```

Откройте `http://localhost:8000`.

Через Docker Compose:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Остановка:

```bash
docker compose -f docker/docker-compose.yml down
```

`data/` подключается в контейнер как `/app/data`. Убедитесь, что Compose передаёт `OPENAI_API_KEY` внутрь контейнера (см. раздел 4). Конфигурация Chat/LLM также должна быть доступна приложению внутри образа.

## 10. Проверка качества и тесты

### Unit-тесты

Из корня проекта:

```bash
pytest notebooks/tests -q
```

### Оценка качества извлечения на каталоге

`quality.eval_extraction` проверяет extraction на синтетических описаниях, созданных из товаров с заполненными атрибутами. Для неё нужен `catalog.sqlite` с таблицей `params` и подготовленная `ideal_attribute_schema.json`.

Из папки `notebooks/`:

```bash
python -m quality.eval_extraction \
  --catalog search/catalog_analysis/catalog.sqlite \
  --n 10

python -m quality.eval_extraction \
  --catalog search/catalog_analysis/catalog.sqlite \
  --n 100
```

Результаты по умолчанию сохраняются в `reports/eval_extraction/`. Проверка обращается к LLM API и может расходовать токены.

## 11. Краткая последовательность команд

Ниже — полный порядок с учётом отдельных источников данных. Предполагается, что входные файлы уже разложены по путям из раздела 5 и ключи настроены.

```bash
# Из корня проекта: нормализация
cd notebooks
python -m normalization.main

# EDA
python -m eda.run_eda

# Схема и поисковые словари EDA
python eda/build_ideal_schema.py
python eda/build_search_dictionaries.py

# Отдельный каталог для RAG из notebooks/search/skus.pkl
python search/analyse_mvd.py

# Создать data/rag.sqlite и индексируемые строки
python search/make_vectors.py index \
  --db search/catalog_analysis/catalog.sqlite \
  --out ../data/rag.sqlite \
  --cap 200

# Словари брендов и моделей в ту же БД
python search/make_dicts.py build \
  --db search/catalog_analysis/catalog.sqlite \
  --out ../data/rag.sqlite

# Эмбеддинги: тестовая партия, затем все оставшиеся строки
python search/make_vectors.py embed --out ../data/rag.sqlite --limit 1000
python search/make_vectors.py embed --out ../data/rag.sqlite
python search/make_vectors.py stats --out ../data/rag.sqlite

# Справочник для проверки качества (рекомендуется)
python -m quality.attr_check build \
  --values search/catalog_analysis/category_values.csv \
  --db ../data/rag.sqlite

# Вернуться в корень и запустить веб-приложение
cd ..
uvicorn app.app:app --app-dir notebooks --host 0.0.0.0 --port 8000
```

`OPENAI_API_KEY` должен быть задан до команд `embed`, `search.py eval` и запуска приложения. Для запуска приложения также нужна корректная настройка Chat/LLM API в `notebooks/config.py`.
