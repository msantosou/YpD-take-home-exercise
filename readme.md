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
