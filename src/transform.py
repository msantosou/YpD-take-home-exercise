import math
import re
from datetime import datetime
from difflib import SequenceMatcher

import pandas as pd


EUR_TO_USD = 1.10
GBP_TO_USD = 1.27
JPY_TO_USD = 1 / 150

MISSING_VALUES = {
    "n/a",
    "na",
    "nan",
    "none",
    "null",
    "not disclosed",
    "undisclosed",
    "missing",
    "",
    "not available",
}

CATEGORY_MAPPING = {
    "ai/ml": "AI_ML",
    "ai & ml": "AI_ML",
    "ai and ml": "AI_ML",
    "artificial intelligence": "AI_ML",
    "machine learning": "AI_ML",
    "ai": "AI_ML",
    "ml": "AI_ML",
    "cloud": "CLOUD",
    "cloud computing": "CLOUD",
    "data analytics": "DATA_ANALYTICS",
    "analytics": "DATA_ANALYTICS",
    "cybersecurity": "CYBERSECURITY",
    "cyber security": "CYBERSECURITY",
    "fintech": "FINTECH",
    "financial technology": "FINTECH",
    "saas": "SAAS",
    "software as a service": "SAAS",
}

COMPANY_ALIASES = {
    "aws": "Amazon Web Services",
    "amazon web services aws": "Amazon Web Services",
    "open ai": "OpenAI",
    "openai inc": "OpenAI",
    "nvidia corporation": "NVIDIA",
    "nvidia corp": "NVIDIA",
    "databricks inc": "Databricks",
    "snowflake inc": "Snowflake",
    "mongodb inc": "MongoDB",
    "meta ai research": "Meta AI",
}


def _parse_numeric_amount(text):
    if text is None:
        return None

    text = str(text).strip().upper()

    if not text or text in {"NAN", "NULL", "NONE", "N/A", "NA"}:
        return None

    text = text.replace(",", "")

    multiplier = 1

    if re.search(r"\bBILLION\b", text):
        multiplier = 1_000_000_000
        text = re.sub(r"\bBILLION\b", "", text)

    elif re.search(r"\bMILLION\b", text):
        multiplier = 1_000_000
        text = re.sub(r"\bMILLION\b", "", text)

    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]

    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]

    text = text.strip()

    try:
        numeric_value = float(text)
    except ValueError:
        return None

    if not math.isfinite(numeric_value):
        return None

    return numeric_value * multiplier


def parse_arr_usd(value):
    """Parse messy ARR/revenue text and return normalized USD as an integer."""
    if value is None:
        return None

    text = str(value).strip()

    if not text or text.lower() in MISSING_VALUES:
        return None

    text_upper = text.upper()

    if "€" in text or "EUR" in text_upper:
        conversion_rate = EUR_TO_USD
    elif "£" in text or "GBP" in text_upper:
        conversion_rate = GBP_TO_USD
    elif "¥" in text or "JPY" in text_upper:
        conversion_rate = JPY_TO_USD
    else:
        conversion_rate = 1.0

    cleaned = text_upper

    for token in ["USD", "EUR", "GBP", "JPY", "$", "€", "£", "¥"]:
        cleaned = cleaned.replace(token, "")

    cleaned = cleaned.strip()

    range_parts = re.split(r"\s*[-–—]\s*", cleaned)

    if len(range_parts) == 2:
        first_value = _parse_numeric_amount(range_parts[0])
        second_value = _parse_numeric_amount(range_parts[1])

        if first_value is None or second_value is None:
            return None

        midpoint = (first_value + second_value) / 2
        usd_value = midpoint * conversion_rate
    else:
        parsed_value = _parse_numeric_amount(cleaned)

        if parsed_value is None:
            return None

        usd_value = parsed_value * conversion_rate

    if not math.isfinite(usd_value):
        return None

    return int(round(usd_value))


def parse_published_date(value, ambiguous_day_first=False):
    """Parse messy publication dates into UTC-aware pandas Timestamps."""
    if value is None:
        return pd.NaT

    text = str(value).strip()

    if text.lower() in MISSING_VALUES:
        return pd.NaT

    known_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
    ]

    for fmt in known_formats:
        try:
            parsed_date = datetime.strptime(text, fmt)
            return pd.Timestamp(parsed_date, tz="UTC")
        except ValueError:
            pass

    try:
        return pd.to_datetime(
            text,
            errors="raise",
            dayfirst=ambiguous_day_first,
            utc=True,
        )
    except (ValueError, TypeError):
        return pd.NaT


def normalize_category(value):
    """Normalize article categories into a controlled taxonomy."""
    if value is None:
        return None

    text = str(value).strip()

    if text.lower() in MISSING_VALUES:
        return None

    normalized_text = text.lower()
    normalized_text = normalized_text.replace("&", "and")
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    if normalized_text in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[normalized_text]

    return normalized_text.upper().replace(" ", "_")


def _normalize_company_name(value):
    """Normalize company text for matching only."""
    if value is None:
        return None

    text = str(value).strip().lower()

    if text in MISSING_VALUES:
        return None

    text = text.replace("&", "and")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def resolve_company_name(value, canonical_companies, fuzzy_threshold=0.90):
    """
    Resolve a source company name to a canonical metadata company.

    Returns None when no sufficiently reliable match exists.
    The original source company remains available in fact_article_arr.
    """
    normalized_value = _normalize_company_name(value)

    if normalized_value is None:
        return None

    canonical_lookup = {
        _normalize_company_name(company): company
        for company in canonical_companies
    }

    if normalized_value in canonical_lookup:
        return canonical_lookup[normalized_value]

    if normalized_value in COMPANY_ALIASES:
        alias_target = COMPANY_ALIASES[normalized_value]

        if alias_target in canonical_companies:
            return alias_target

    best_match = None
    best_score = 0

    for normalized_canonical, canonical_name in canonical_lookup.items():
        score = SequenceMatcher(
            None,
            normalized_value,
            normalized_canonical,
        ).ratio()

        if score > best_score:
            best_score = score
            best_match = canonical_name

    if best_score >= fuzzy_threshold:
        return best_match

    return None


def derive_company_size(employee_count):
    """Return SMALL, MEDIUM, LARGE, or None from employee count."""
    if employee_count is None:
        return None

    text = str(employee_count).strip()

    if text.lower() in MISSING_VALUES:
        return None

    try:
        count = int(float(text))
    except (ValueError, TypeError):
        return None

    if count < 0:
        return None
    if count < 10_000:
        return "SMALL"
    if count <= 30_000:
        return "MEDIUM"
    return "LARGE"


def derive_company_age(founded_year, published_date):
    """Calculate company age as published year minus founded year."""
    if founded_year is None:
        return None

    founded_text = str(founded_year).strip().lower()

    if founded_text in MISSING_VALUES:
        return None

    try:
        founded_year = int(float(founded_year))
    except (ValueError, TypeError):
        return None

    if published_date is None or pd.isna(published_date):
        return None

    try:
        published_date = pd.Timestamp(published_date)
    except (ValueError, TypeError):
        return None

    company_age = published_date.year - founded_year

    if company_age < 0:
        return None

    return company_age


def build_dim_company(companies_df):
    """Build the canonical company dimension."""
    dim_company = companies_df.copy(deep=True)

    dim_company["company_size_category"] = (
        dim_company["employee_count"].apply(derive_company_size)
    )

    return dim_company


def build_fact_article_arr(articles_df, dim_company):
    """Build the article-level ARR fact table."""
    canonical_companies = dim_company["company_name"].tolist()

    fact_article_arr = articles_df.copy(deep=True)

    fact_article_arr["arr_usd"] = (
        fact_article_arr["revenue"].apply(parse_arr_usd)
    )

    fact_article_arr["published_date_clean"] = (
        fact_article_arr["published_date"].apply(parse_published_date)
    )

    fact_article_arr["category_clean"] = (
        fact_article_arr["category"].apply(normalize_category)
    )

    fact_article_arr["company_name_resolved"] = (
        fact_article_arr["company_name"].apply(
            lambda value: resolve_company_name(
                value,
                canonical_companies,
            )
        )
    )

    return fact_article_arr


def build_fact_article_arr_enriched(fact_article_arr, dim_company):
    """Enrich article ARR fact records with company metadata."""
    enriched = (
        fact_article_arr.merge(
            dim_company,
            left_on="company_name_resolved",
            right_on="company_name",
            how="left",
            suffixes=("", "_y"),
        )
        .drop("company_name_y", axis="columns")
    )

    enriched["company_age"] = enriched.apply(
        lambda row: derive_company_age(
            row["founded_year"],
            row["published_date_clean"],
        ),
        axis=1,
    )

    return enriched


def build_ai_articles_enriched(fact_article_arr_enriched):
    """
    Create the required AI article export.

    Assumes embedding_serialized has already been added by semantic_search.py.
    """
    filtered = (
        fact_article_arr_enriched[
            (
                (fact_article_arr_enriched["category_clean"] == "AI_ML")
                | (fact_article_arr_enriched["industry"] == "AI/ML")
            )
            & (
                fact_article_arr_enriched["published_date_clean"]
                >= pd.Timestamp("2022-01-01", tz="UTC")
            )
            & (
                fact_article_arr_enriched["published_date_clean"]
                < pd.Timestamp("2025-01-01", tz="UTC")
            )
            & fact_article_arr_enriched["arr_usd"].notna()
            & (fact_article_arr_enriched["arr_usd"] > 50_000_000)
        ]
        .copy(deep=True)
    )

    return (
        filtered[
            [
                "article_id",
                "title",
                "company_name_resolved",
                "published_date_clean",
                "category_clean",
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
                "embedding_serialized",
            ]
        ]
        .rename(
            columns={
                "company_name_resolved": "company_name",
                "published_date_clean": "published_date",
                "category_clean": "category",
                "embedding_serialized": "embedding",
            }
        )
    )
