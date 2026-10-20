import pandas as pd


REQUIRED_AI_COLUMNS = {
    "article_id",
    "title",
    "company_name",
    "published_date",
    "category",
    "arr_usd",
    "summary",
    "url",
    "industry",
    "founded_year",
    "headquarters",
    "employee_count",
    "is_public",
    "stock_ticker",
    "company_age",
    "company_size_category",
    "embedding",
}


def validate_unique_key(df, key, dataset_name):
    """Raise when a modeled dataset contains duplicate keys."""
    duplicate_count = df.duplicated(subset=[key], keep=False).sum()

    if duplicate_count:
        raise ValueError(
            f"{dataset_name}: found {duplicate_count} rows with "
            f"duplicated {key}"
        )


def validate_required_columns(df, required_columns, dataset_name):
    """Raise when required columns are missing."""
    missing = set(required_columns) - set(df.columns)

    if missing:
        raise ValueError(
            f"{dataset_name}: missing columns: {sorted(missing)}"
        )


def validate_arr_values(fact_article_arr):
    """ARR values must be positive when populated."""
    invalid = (
        fact_article_arr["arr_usd"].notna()
        & (fact_article_arr["arr_usd"] <= 0)
    )

    if invalid.any():
        raise ValueError(
            f"fact_article_arr: found {invalid.sum()} "
            "non-positive ARR values"
        )


def validate_embedding_dimensions(
    fact_article_arr_enriched,
    expected_dimension=384,
):
    """Every populated embedding must have the expected dimensionality."""
    if "embedding" not in fact_article_arr_enriched.columns:
        raise ValueError(
            "fact_article_arr_enriched: embedding column is missing"
        )

    invalid = (
        fact_article_arr_enriched["embedding"]
        .apply(
            lambda vector: (
                vector is None
                or len(vector) != expected_dimension
            )
        )
    )

    if invalid.any():
        raise ValueError(
            "fact_article_arr_enriched: "
            f"{invalid.sum()} embeddings do not have "
            f"dimension {expected_dimension}"
        )


def validate_ai_articles_enriched(ai_articles_enriched):
    """Validate all business rules for the required AI export."""
    validate_required_columns(
        ai_articles_enriched,
        REQUIRED_AI_COLUMNS,
        "ai_articles_enriched",
    )

    if not (
        ai_articles_enriched["arr_usd"] > 50_000_000
    ).all():
        raise ValueError(
            "ai_articles_enriched contains ARR <= $50M"
        )

    if not (
        ai_articles_enriched["published_date"]
        .dt.year
        .between(2022, 2024)
    ).all():
        raise ValueError(
            "ai_articles_enriched contains dates outside 2022-2024"
        )

    if not (
        (ai_articles_enriched["category"] == "AI_ML")
        | (ai_articles_enriched["industry"] == "AI/ML")
    ).all():
        raise ValueError(
            "ai_articles_enriched contains non-AI records"
        )


def validate_all(
    dim_company,
    fact_article_arr,
    fact_article_arr_enriched,
    ai_articles_enriched,
):
    """Run the pipeline's core model-level data quality checks."""
    validate_unique_key(
        dim_company,
        "company_name",
        "dim_company",
    )

    validate_unique_key(
        fact_article_arr,
        "article_id",
        "fact_article_arr",
    )

    validate_unique_key(
        fact_article_arr_enriched,
        "article_id",
        "fact_article_arr_enriched",
    )

    validate_arr_values(fact_article_arr)

    validate_embedding_dimensions(
        fact_article_arr_enriched,
    )

    validate_ai_articles_enriched(
        ai_articles_enriched,
    )
