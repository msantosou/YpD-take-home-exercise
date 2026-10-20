# Data Architecture

## 1. Architecture Overview

The pipeline transforms two raw source datasets into analytical fact and dimension models, a required AI-focused downstream dataset, and an optional DuckDB analytical database.

The architecture is designed as a small local implementation, to allow the same workflow to scale into a production batch pipeline some changes may be done to make the pipeline incremental, for example.

```text
                        ┌────────────────────────┐
                        │     Source Files       │
                        │                        │
                        │ tech_news.csv          │
                        │ company_metadata.json  │
                        └───────────┬────────────┘
                                    │
                                    ▼
                        ┌────────────────────────┐
                        │    Raw / Ingestion     │
                        │                        │
                        │ Preserve source fields │
                        │ articles_df            │
                        │ companies_df           │
                        └───────────┬────────────┘
                                    │
                                    ▼
                        ┌────────────────────────┐
                        │ Cleaning / Staging     │
                        │                        │
                        │ ARR parsing            │
                        │ Date normalization     │
                        │ Category mapping       │
                        │ Company resolution     │
                        └───────────┬────────────┘
                                    │
                                    ▼
                        ┌────────────────────────┐
                        │ Metadata Enrichment    │
                        │                        │
                        │ Industry               │
                        │ Company age            │
                        │ Company size           │
                        │ Other metadata         │
                        └───────────┬────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
          ┌──────────────────┐           ┌──────────────────────┐
          │   dim_company    │           │   fact_article_arr   │
          └─────────┬────────┘           └──────────┬───────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                        ┌────────────────────────┐
                        │ fact_article_arr_      │
                        │ enriched               │
                        └───────────┬────────────┘
                                    │
                     ┌──────────────┴─────────────┐
                     ▼                            ▼
          ┌─────────────────────┐        ┌──────────────────┐
          │ ai_articles_        │        │     DuckDB       │
          │ enriched.csv        │        │                  │
          └─────────────────────┘        │ SQL + vectors    │
                                         └──────────────────┘
```

## 2. Source Layer

### `tech_news.csv`

The source article dataset contains one record per article.

Important source fields include:

* `article_id`
* `title`
* `company_name`
* `published_date`
* `category`
* `revenue`
* `summary`
* `url`
* `author`
* `word_count`

The dataset intentionally contains inconsistent source representations.

Raw source fields are preserved throughout the transformation process whenever they are needed for lineage or auditability.

### `company_metadata.json`

Company metadata is converted from nested JSON into tabular form.

The company name is treated as the canonical business identifier available in the supplied metadata.

Important fields include:

* `company_name`
* `founded_year`
* `headquarters`
* `employee_count`
* `industry`
* `is_public`
* `stock_ticker`

## 3. Transformation Layer

Transformation logic is implemented as reusable Python functions.

### ARR parsing

`parse_arr_usd()` converts source revenue values into normalized integer USD values.

The original `revenue` value is retained.

This is important because ARR values are observations reported by individual articles and must remain traceable to their source.

### Date normalization

`parse_published_date()` converts source publication dates into consistent UTC-aware timestamps.

Derived fields may include:

```text
published_year
published_month
published_quarter
```

Invalid dates are represented as missing values rather than silently corrected.

### Category normalization

`normalize_category()` maps variations of article categories into a controlled taxonomy.

For example:

```text
AI/ML
AI & ML
Artificial Intelligence
Machine Learning
```

map to:

```text
AI_ML
```

### Company resolution

Article company names are matched against canonical company metadata.

Resolution follows:

```text
exact normalized match
        ↓
explicit alias match
        ↓
conservative fuzzy match
        ↓
unresolved
```

The original source company value remains available regardless of resolution outcome.

Resolution metadata can include:

```text
company_name_resolved
match_method
match_score
```

This prevents fuzzy matching logic from becoming invisible to downstream users.

## 4. Data Model

### `dim_company`

Grain:

```text
one row per canonical company_name
```

Primary business key:

```text
company_name
```

The dimension contains relatively stable descriptive company attributes.

Example fields:

```text
company_name
founded_year
headquarters
employee_count
industry
is_public
stock_ticker
company_size_category
```

`company_size_category` is derived from `employee_count`.

The thresholds are:

```text
SMALL   < 10,000
MEDIUM  10,000 - 30,000
LARGE   > 30,000
```

### `fact_article_arr`

Grain:

```text
one row per article_id
```

Business key:

```text
article_id
```

The fact stores each article and its associated ARR observation when the source revenue can be successfully parsed.

Example fields:

```text
article_id
title
company_name
company_name_resolved
published_date
published_date_clean
category
category_clean
revenue
arr_usd
summary
url
author
word_count
```

The relationship is:

```text
dim_company
    1
    │
    │
    N
fact_article_arr
```

A company can therefore have multiple ARR observations across different article publication dates.

## 5. ARR Observation Semantics

`arr_usd` must not be interpreted as the authoritative current ARR attribute of the company.

Instead:

```text
company
+
article
+
published date
+
reported ARR
```

constitutes a source-backed ARR observation.

For example:

```text
Company: Snowflake
Article date: 2023-05-12
Reported ARR: $2.1B
Source article: article_123
```

is interpreted as:

```text
Snowflake had a reported ARR observation of $2.1B
according to article_123 as of 2023-05-12.
```

A later article can produce a different ARR observation without overwriting the earlier observation.

This model preserves analytical history and source lineage.

## 6. `fact_article_arr_enriched`

This dataset extends the article fact with company metadata.

Example fields include:

```text
article_id
title
company_name
published_date_clean
category_clean
arr_usd
summary
url
industry
founded_year
headquarters
employee_count
is_public
stock_ticker
company_size_category
company_age
embedding
```

`company_age` is calculated relative to the article publication year.

Because the source metadata contains only `founded_year`, it is calculated as:

```text
published_year - founded_year
```

rather than pretending an exact incorporation date is available.

This enriched table is convenient for analytical and downstream filtering where denormalized access is useful.

## 7. Required AI Dataset

`ai_articles_enriched.csv` is derived from `fact_article_arr_enriched`.

Selection logic:

```text
(
    normalized article category = AI_ML
    OR
    company industry = AI/ML
)

AND

published year between 2022 and 2024

AND

valid arr_usd > 50,000,000
```

This is treated as a downstream analytical product rather than the core warehouse model.

## 8. Semantic Search

Article semantic embeddings are generated using:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Input text:

```text
title + summary
```

Each article receives a fixed-length 384-dimensional embedding.

The embedding captures semantic meaning and supports similarity search beyond exact keyword matching.

### Vector similarity

Queries are embedded using the same model.

Cosine similarity compares the query embedding to article embeddings.

The semantic search function returns:

```text
article_id
similarity_score
```

ordered from highest similarity to lowest.

## 9. DuckDB and Hybrid Search

DuckDB provides the local analytical database layer.

Tables loaded into DuckDB include:

```text
dim_company
fact_article_arr
fact_article_arr_enriched
ai_articles_enriched
```

Embeddings are stored as a numeric array where possible:

```text
FLOAT[384]
```

rather than plain JSON text.

This allows native vector calculations such as cosine similarity.

Hybrid search combines relational filtering and semantic ranking.

Example:

```text
SQL filters
----------
AI-related
2022-2024
ARR > $50M

        ↓

candidate article subset

        ↓

vector cosine similarity

        ↓

top K semantically similar results
```

This approach is preferable to calculating vector similarity against every record when structured filters can first reduce the candidate set.

## 10. Idempotency

Local pipeline execution is designed to be repeatable.

Generated tables and CSV outputs are recreated from source data rather than appended blindly.

`article_id` is used as the article-level business key.

This ensures rerunning the same batch does not produce multiple copies of the same modeled article.

In a persistent production environment, the same principle could be implemented through:

* `MERGE`
* upsert
* deterministic keys
* partition replacement
* snapshot/version logic

depending on the target platform.

## 11. Data Quality

Data-quality checks cover both transformation correctness and model integrity.

Examples include:

### Article fact

```text
article_id IS NOT NULL
article_id is unique
```

### Company dimension

```text
company_name IS NOT NULL
company_name is unique
```

### ARR

```text
arr_usd > 0 when populated
invalid/missing revenue does not become zero ARR
```

### Dates

```text
valid parsed timestamps
invalid values remain explicitly missing
```

### Company enrichment

```text
matched company names correspond to metadata records
unresolved companies are identifiable
```

### Embeddings

```text
one embedding per eligible article
embedding dimension = 384
```

### AI output

All records must satisfy:

```text
AI category OR AI/ML industry
year between 2022 and 2024
ARR > $50M
```

Reusable transformation functions are covered by automated unit tests.

The development notebook contains additional source profiling and exploratory validation.

## 12. Reliability Beyond Local Batch

The local implementation uses Pandas, local files, and DuckDB because the supplied dataset is small.

For larger or continuously arriving datasets, the logical architecture would remain similar while the execution technologies could change.

### Storage

Raw files would be landed into durable object storage such as:

```text
Amazon S3
Azure Data Lake Storage
Google Cloud Storage
```

Raw source data would be immutable and partitioned by ingestion date or source date.

### Processing

Pandas transformations could migrate to a distributed engine such as:

```text
Spark
Databricks
AWS Glue
```

if volume exceeded single-machine limits.

Transformation functions would retain the same business rules.

### Orchestration

The local entry-point script could become a scheduled workflow in:

```text
Apache Airflow
Dagster
Prefect
```

A production DAG could contain stages such as:

```text
ingest
  ↓
validate raw sources
  ↓
transform
  ↓
validate modeled datasets
  ↓
publish
  ↓
update vector index
```

### Incremental Processing

Rather than reprocessing all historical data, new article batches could be incrementally processed using:

```text
article_id
```

as the deterministic article key.

Existing records could be updated using MERGE/upsert semantics.

### Backfills

Backfills should use the same transformation code as normal incremental runs.

A historical date range could be reprocessed into temporary or partition-scoped outputs and validated before replacing production data.

This avoids maintaining separate backfill logic.

### Schema Evolution

Incoming schemas would be validated against an expected contract.

Changes would be classified as:

```text
compatible
breaking
unexpected
```

Unexpected required-field changes should fail the pipeline rather than silently corrupt modeled outputs.

Optional new columns can be introduced through explicit model version changes.

### Observability

Production execution should record:

```text
input record count
output record count
ARR parsing failures
date parsing failures
unresolved companies
duplicate keys
pipeline runtime
data freshness
```

Alerting could be triggered when these metrics exceed agreed thresholds.

### Data Lineage

The lineage path remains:

```text
source article
    ↓
article_id
    ↓
fact_article_arr
    ↓
enriched fact / downstream exports
```

The original revenue value and source article remain available so every ARR observation can be traced back to its source.

### Semantic Search at Scale

For the local exercise, DuckDB can perform vector similarity efficiently over the small dataset.

At significantly larger scale, embeddings could be stored in a dedicated vector-capable database or search engine.

The logical contract would remain:

```text
article_id
embedding
embedding_model
embedding_version
```

Versioning the embedding model would be important to ensure embeddings generated by different models are not silently mixed.

## 13. Trade-offs

The design intentionally avoids unnecessary complexity for a dataset of 750 articles.

A separate ARR-observation fact table was considered but not required because the supplied dataset has effectively one potential ARR observation per article.

Therefore:

```text
article_id
```

is sufficient as the fact grain.

If future articles could contain multiple companies, multiple financial metrics, or multiple ARR observations, the model should evolve toward:

```text
dim_article
fact_financial_observation
```

with potentially multiple observations per article.

The current model optimizes for simplicity, auditability, and the required query patterns without introducing structures unsupported by the source data.
