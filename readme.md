# YipitData Data Engineering Take-Home Exercise

## Overview

This project implements a local Python data pipeline that processes a synthetic technology-news dataset and company metadata into analytical data models that support company ARR analysis over time.

The pipeline performs:

* source ingestion from CSV and JSON
* ARR parsing and USD normalization
* publication date normalization
* article category standardization
* company name resolution
* company metadata enrichment
* company size and company age derivation
* dimensional and fact modeling
* generation of the required AI article dataset
* article embeddings for semantic similarity search
* optional DuckDB integration for analytical and hybrid search
* data quality validation

The primary analytical grain is one row per `article_id` in the article ARR fact table.


## Architecture and Data Flow

The solution is intentionally small enough to run locally, while keeping clear boundaries between ingestion, transformation, modeling, validation, semantic search, and persistence.

```text
                    ┌──────────────────────────┐
                    │       Raw Sources        │
                    │                          │
                    │ tech_news.csv            │
                    │ company_metadata.json    │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │   ingest.py    │
                        │                │
                        │ Load CSV/JSON  │
                        │ Preserve raw   │
                        │ source fields  │
                        └───────┬────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │    transform.py     │
                     │                     │
                     │ ARR normalization   │
                     │ Date normalization  │
                     │ Category mapping    │
                     │ Company resolution  │
                     │ Metadata enrichment │
                     └─────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
             ┌─────────────┐      ┌──────────────────┐
             │ dim_company │      │ fact_article_arr │
             └──────┬──────┘      └────────┬─────────┘
                    │                      │
                    └──────────┬───────────┘
                               ▼
                 ┌───────────────────────────┐
                 │ fact_article_arr_enriched │
                 └─────────────┬─────────────┘
                               │
                  ┌────────────┼─────────────┐
                  ▼            ▼             ▼
      ┌─────────────────┐  ┌────────────┐  ┌────────────────┐
      │ AI article CSV  │  │ Embeddings │  │ Data Quality   │
      │ required output │  │ + semantic │  │ validations    │
      └─────────────────┘  │ search     │  └────────────────┘
                           └──────┬─────┘
                                  ▼
                            ┌──────────┐
                            │ DuckDB   │
                            │ SQL +    │
                            │ vectors  │
                            └──────────┘
```

The notebook is used for exploratory profiling and manual testing. The production-like execution path is `src/run_pipeline.py`, which keeps the DataFrames in the same Python process and passes them explicitly between ingestion, transformation, validation, export, and DuckDB-loading stages.

### Main modeled relationships

```text
dim_company
    1
    │
    │ company_name / company_name_resolved
    │
    N
fact_article_arr
    │
    │ same article grain
    ▼
fact_article_arr_enriched
```

`fact_article_arr` uses `article_id` as its grain. A company can therefore have many article-level ARR observations over time.

## Key Design Decisions

### One article fact instead of separate article and ARR facts

The current source provides at most one ARR observation per article, so both entities have the same practical grain. A separate ARR fact would therefore introduce an unnecessary one-to-one relationship.

If future articles could contain multiple companies, multiple ARR values, or multiple financial metrics, the model should evolve toward a separate article dimension/fact and a financial-observation fact.

### ARR as an observation, not company master data

`arr_usd` represents what a specific article reported for a company as of the article publication date.

The model therefore preserves:

- the original source `revenue`
- the normalized `arr_usd`
- the article ID
- the publication date
- the article URL

This keeps every ARR observation auditable and prevents a reported article value from being silently treated as an authoritative company attribute.

### Pandas rather than Spark

The supplied dataset is small, so distributed processing would add complexity without providing meaningful benefit. The transformation rules are implemented as reusable functions so the same business logic could later move to Spark or another distributed engine if data volume required it.

### Conservative company resolution

Company matching follows:

```text
normalized exact match
        ↓
explicit alias
        ↓
conservative fuzzy match
        ↓
unresolved
```

The original source company value is always preserved. An unresolved company is preferable to an incorrect match.

### DuckDB `FLOAT[384]` embeddings

The selected sentence-transformer model produces fixed 384-dimensional embeddings. In DuckDB, embeddings are stored as numeric arrays instead of plain text so native vector operations such as cosine similarity can be used directly.

## Reliability and Data Quality

The pipeline validates model invariants rather than treating successful code execution as sufficient evidence of successful processing.

Important checks include:

- `article_id` is unique and non-null in the article fact
- `company_name` is unique and non-null in `dim_company`
- enriched fact row count matches the base fact row count
- populated ARR values are positive
- invalid or undisclosed revenue values do not become zero ARR
- required output columns exist
- embedding vectors contain 384 values
- the AI export satisfies all required date, category/industry, and ARR filters
- AI export records remain traceable to the enriched fact
- unresolved company matches are identifiable

For the local implementation, modeled outputs are recreated instead of blindly appended. This makes repeated runs deterministic and avoids duplicate records for the same source batch.

In a persistent warehouse, the same behavior would typically be implemented with deterministic business keys and `MERGE`/upsert logic using `article_id`.

## Hybrid Search Flow

Hybrid search combines structured SQL filtering with semantic vector similarity.

```text
SQL filters
-----------
AI-related
2022-2024
ARR > $50M
      │
      ▼
candidate article subset
      │
      ▼
query embedding
      +
article embeddings
      │
      ▼
cosine similarity
      │
      ▼
Top-K semantically similar articles
```

Example query:

```text
companies building generative AI infrastructure
```

The structured filters ensure the candidates satisfy the requested analytical conditions. Cosine similarity then ranks those candidates by semantic meaning rather than exact keyword overlap.

## Production Evolution

The local implementation intentionally uses lightweight tools, but the logical architecture can scale without changing the core data contracts.

| Local implementation | Production evolution |
|---|---|
| CSV / JSON files | S3, ADLS, GCS or another durable object store |
| Pandas | Spark, Databricks, Glue, or another distributed engine |
| `run_pipeline.py` | Airflow, Dagster, Prefect, or managed orchestration |
| CSV modeled outputs | Delta, Iceberg, warehouse tables |
| Local validations | Automated DQ metrics, alerts, SLAs/SLOs |
| DuckDB vector search | Vector-capable analytical/search platform |

A production workflow would additionally support:

- incremental processing by deterministic `article_id`
- backfills using the same transformation logic as normal runs
- schema-contract validation before transformation
- monitoring for parse failures, unresolved companies, duplicates, freshness, and runtime
- explicit versioning of the embedding model and vector index

## Live Review / Presentation Guide

For a 45-minute review, the solution can be presented in roughly 15-20 minutes, leaving the remaining time for discussion and live coding.

Recommended flow:

1. **Problem and objective** — explain ARR history + semantic search.
2. **Architecture** — walk through ingestion → transformations → modeling → validation → DuckDB.
3. **Data model** — explain the grains of `dim_company` and `fact_article_arr`.
4. **Cleaning decisions** — show ARR, date, category, and company-resolution examples.
5. **Lineage and idempotency** — explain why raw revenue and article references are preserved.
6. **Data quality** — show key validations and failure conditions.
7. **Semantic search** — explain `title + summary` → embedding → cosine similarity.
8. **Hybrid search** — show SQL filters + vector ranking.
9. **Production evolution** — explain how the local solution would scale.
10. **Demo** — query ARR history, source lineage, and hybrid search in DuckDB.

Suggested live-demo queries:

### ARR history for one company

```sql
SELECT
    company_name_resolved,
    published_date_clean,
    arr_usd,
    title,
    url
FROM fact_article_arr_enriched
WHERE company_name_resolved = 'Snowflake'
  AND arr_usd IS NOT NULL
ORDER BY published_date_clean;
```

### Source lineage

```sql
SELECT
    article_id,
    company_name_resolved,
    revenue,
    arr_usd,
    published_date_clean,
    url
FROM fact_article_arr_enriched
WHERE arr_usd IS NOT NULL
LIMIT 10;
```

### Validate AI downstream output

```sql
SELECT COUNT(*) AS invalid_rows
FROM ai_articles_enriched
WHERE NOT (
    category = 'AI_ML'
    OR industry = 'AI/ML'
)
OR published_date < TIMESTAMPTZ '2022-01-01'
OR published_date >= TIMESTAMPTZ '2025-01-01'
OR arr_usd <= 50000000
OR arr_usd IS NULL;
```

Expected result:

```text
invalid_rows = 0
```

### Hybrid-search example

Use a semantic query such as:

```text
companies building generative AI infrastructure
```

with:

```text
AI-related
2022-2024
ARR > $50M
Top 5 results
```

The most important design points to be prepared to defend are:

- why the article and ARR observation share one fact at the current grain
- why ARR is modeled as a source-backed observation
- why unresolved company names are preserved
- why Pandas is appropriate for this data volume
- why DuckDB is appropriate for local analytical and vector querying
- how idempotency, backfills, schema changes, and observability would work beyond the local batch


## Project Structure

```text
YpD-take-home-exercise/
│
├── data/
│   ├── raw/
│   │   ├── tech_news.csv
│   │   └── company_metadata.json
│   │
│   └── output/
│       ├── dim_company.csv
│       ├── fact_article_arr.csv
│       ├── fact_article_arr_enriched.csv
│       └── ai_articles_enriched.csv
│
├── src/
│   ├── ingest.py
│   ├── transform.py
│   ├── duckdb_load.py
│   ├── validations.py
│   └── run_pipeline.py
│
├── tests/
│   └── test_transformations.py
│
├── notebooks/
│   └── data_analysis.ipynb
│
├── README.md
├── DATA_ARCHITECTURE.md
├── requirements.txt
├── .gitignore
└── ypd_take_home.duckdb        # optional
```

The exact filenames may differ, but the pipeline is organized so that ingestion, transformation, validation, storage, and exploratory analysis remain separate responsibilities.

## System Requirements

Recommended environment:

* Python 3.10+
* Linux, macOS, or Windows
* approximately 2 GB of free memory for the local workload
* internet access during the initial installation of Python packages and embedding model
* Git

The dataset is small and is designed to run locally.

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd YpD-take-home-exercise
```

Create a project-specific virtual environment:

```bash
python3 -m venv .venv_ypd
```

Activate it:

Linux/macOS:

```bash
source .venv_ypd/bin/activate
```

Windows:

```bash
.venv_ypd\Scripts\activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For notebook usage, the project environment can be registered as a Jupyter kernel:

```bash
python -m ipykernel install \
  --user \
  --name ypd-take-home \
  --display-name "Python (YpD Take Home)"
```

## Input Data

The pipeline expects two source files:

```text
data/raw/tech_news.csv
data/raw/company_metadata.json
```

`tech_news.csv` contains technology-news articles with intentionally inconsistent fields including company names, publication dates, categories, and revenue values.

`company_metadata.json` contains the canonical company metadata used for enrichment.

## Running the Pipeline

The preferred execution method is a single pipeline entry point:

```bash
python src/run_pipeline.py
```

The pipeline performs the following stages:

```text
Raw sources
    ↓
Ingestion
    ↓
Cleaning and normalization
    ↓
Company resolution and enrichment
    ↓
Fact and dimension modeling
    ↓
Data quality validation
    ↓
CSV exports
    ↓
DuckDB loading
```

The individual stages may also be executed independently during development:

```bash
python src/ingest.py
python src/transform.py
python src/validations.py
python src/duckdb_load.py
```

## Data Cleaning Rules

### ARR normalization

The source `revenue` column is interpreted as a reported ARR observation when it contains a valid value.

The parser supports:

* USD
* EUR
* GBP
* JPY
* millions and billions
* abbreviated values such as `500M` and `5.2B`
* explicit forms such as `5.2 billion`
* comma-separated values
* ranges such as `$10M - $20M`

For ranges, the midpoint is used.

Currency conversion uses the fixed rates defined by the assignment.

The original `revenue` string is retained for lineage and audit purposes.

Missing or undisclosed revenue values are not converted into valid ARR observations.

### Publication dates

Multiple date formats are normalized into a Pandas timestamp.

Dates are stored consistently using UTC.

Ambiguous numeric dates default to month-first interpretation unless explicitly configured otherwise.

Derived values include:

* publication year
* publication month
* publication quarter

### Category normalization

Source article categories are mapped into a controlled taxonomy.

For example:

```text
AI/ML
AI & ML
Artificial Intelligence
Machine Learning
```

are normalized to:

```text
AI_ML
```

Unknown categories are preserved rather than silently discarded.

### Company resolution

Company names are matched against the canonical company metadata using:

1. normalized exact matching
2. explicit aliases
3. conservative fuzzy matching

Matching metadata such as method and similarity score can be retained for auditing.

Unresolved company values remain traceable through the original source company field.

## Data Model

The modeled datasets are:

### `dim_company`

Grain:

```text
one row per canonical company_name
```

Contains company attributes such as:

* company name
* founded year
* headquarters
* employee count
* industry
* public/private status
* stock ticker
* company size category

### `fact_article_arr`

Grain:

```text
one row per article_id
```

Contains the source article and its ARR observation when available.

Important fields include:

* article ID
* title
* source company name
* resolved company name
* publication date
* category
* original revenue value
* normalized ARR in USD
* summary
* URL
* author
* word count

A valid `arr_usd` represents a reported ARR observation for the article's company as of the article publication date.

The ARR value is treated as an observation sourced from the article, not as authoritative company master data.

### `fact_article_arr_enriched`

This table extends `fact_article_arr` with company metadata such as:

* industry
* founded year
* headquarters
* employee count
* public/private status
* stock ticker
* company size category
* company age
* article embedding

This table supports analytical filtering and semantic search.

### `ai_articles_enriched`

Required downstream export containing articles where:

* article category indicates AI / Machine Learning OR the company industry is AI / ML
* article date is between 2022 and 2024
* valid ARR is greater than USD 50 million

## Regenerating CSV Outputs

Run:

```bash
python src/run_pipeline.py
```

This recreates:

```text
data/output/dim_company.csv
data/output/fact_article_arr.csv
data/output/fact_article_arr_enriched.csv
data/output/ai_articles_enriched.csv
```

Outputs are recreated rather than appended to, making repeated execution idempotent for the local batch workflow.

## Example Pandas Usage

### ARR observations for a company over time

```python
fact_article_arr_enriched[
    fact_article_arr_enriched["company_name_resolved"] == "Snowflake"
][
    [
        "article_id",
        "published_date_clean",
        "arr_usd",
        "url"
    ]
].sort_values("published_date_clean")
```

### Articles with ARR greater than USD 50 million

```python
fact_article_arr_enriched[
    fact_article_arr_enriched["arr_usd"] > 50_000_000
]
```

### AI-related articles

```python
fact_article_arr_enriched[
    (fact_article_arr_enriched["category_clean"] == "AI_ML")
    | (fact_article_arr_enriched["industry"] == "AI/ML")
]
```

## Semantic Search

Article embeddings are generated from:

```text
title + summary
```

using:

```text
sentence-transformers/all-MiniLM-L6-v2
```

The model produces a fixed-size embedding vector for each article.

Semantic search compares a query embedding to article embeddings using cosine similarity.

Example:

```python
find_similar_articles(
    query_text="cloud companies expanding artificial intelligence infrastructure",
    top_k=5
)
```

The function returns article IDs and similarity scores ranked from most to least semantically similar.

## DuckDB

DuckDB is used as the local analytical store.

The modeled CSV files can be loaded into:

```text
ypd_take_home.duckdb
```

Example:

```sql
SELECT
    company_name_resolved,
    published_date_clean,
    arr_usd
FROM fact_article_arr_enriched
WHERE arr_usd > 50000000
ORDER BY published_date_clean;
```

DuckDB is also used for hybrid search, combining SQL filters with semantic vector similarity.

Example use case:

```text
AI-related articles
published between 2022 and 2024
ARR > $50M
semantically similar to a supplied query
```

The persisted DuckDB database is optional. The CSV exports remain the canonical submitted modeled outputs.

## Required Query Patterns

The modeled datasets support the four analytical requirements of the assignment.

### ARR observations over time
```sql
SELECT
    company_name_resolved AS company_name,
    published_date_clean AS observation_date,
    arr_usd,
    article_id,
    title,
    url
FROM fact_article_arr_enriched
WHERE company_name_resolved = 'Snowflake'
  AND arr_usd IS NOT NULL
ORDER BY published_date_clean;
```

### Source lineage for an ARR observation
```sql
SELECT
    article_id,
    company_name,
    company_name_resolved,
    published_date,
    revenue AS source_revenue,
    arr_usd,
    title,
    url
FROM fact_article_arr
WHERE article_id = '<ARTICLE_ID>';
```

### Structured article filtering
```sql
SELECT
    article_id,
    title,
    company_name_resolved,
    published_date_clean,
    category_clean,
    industry,
    arr_usd
FROM fact_article_arr_enriched
WHERE (
        category_clean = 'AI_ML'
        OR industry = 'AI/ML'
      )
  AND published_date_clean >= TIMESTAMPTZ '2022-01-01'
  AND published_date_clean < TIMESTAMPTZ '2025-01-01'
  AND arr_usd > 50000000;
```
### Idempotency / duplicate validation
```sql
SELECT
    article_id,
    COUNT(*) AS record_count
FROM fact_article_arr
GROUP BY article_id
HAVING COUNT(*) > 1;
```

## Data Validation

Validation includes checks for:

* duplicate `article_id`
* duplicate company dimension keys
* invalid ARR values
* invalid publication dates
* unresolved company names
* ARR parsing behavior
* company size boundaries
* category mappings
* required downstream filters
* embedding dimensions
* required output columns

Unit tests are implemented for reusable transformation functions.

The notebook also contains exploratory source profiling and validation performed during development.

## Idempotency

The pipeline recreates modeled outputs from the original input data instead of appending to existing output files.

`article_id` is treated as the article-level business key.

This prevents repeated executions against the same source batch from creating duplicate modeled records.

## Assumptions and Limitations

* Every valid source revenue value is interpreted as an ARR observation as instructed by the assignment.
* ARR observations are source-backed observations and are not treated as authoritative company master attributes.
* Company age is calculated using `published_year - founded_year` because only the founding year is available.
* Ambiguous numeric dates use a documented default interpretation.
* Fuzzy company matches use a conservative threshold to avoid incorrect enrichment.
* Embeddings summarize article semantic meaning and are not intended to reconstruct the original article text.
