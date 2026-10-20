from pathlib import Path
import json

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1] / "data/raw/"

TECH_NEWS_FILE = PROJECT_ROOT / "tech_news.csv"
COMPANY_METADATA_FILE = PROJECT_ROOT / "company_metadata.json"

def load_articles(file_path=TECH_NEWS_FILE):
    """Load the raw technology-news CSV as strings."""
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Article source file not found: {file_path}")

    return pd.read_csv(file_path, dtype=str)


def load_company_metadata(file_path=COMPANY_METADATA_FILE):
    """Load company metadata JSON and convert it to tabular form."""
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Company metadata file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as file:
        company_metadata = json.load(file)

    companies_df = (
        pd.DataFrame.from_dict(company_metadata, orient="index", dtype=str)
        .reset_index()
        .rename(columns={"index": "company_name"})
    )

    return companies_df


def load_sources(
    tech_news_file=TECH_NEWS_FILE,
    company_metadata_file=COMPANY_METADATA_FILE,
):
    """
    Load both project sources.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        articles_df, companies_df
    """
    articles_df = load_articles(tech_news_file)
    companies_df = load_company_metadata(company_metadata_file)

    return articles_df, companies_df


if __name__ == "__main__":
    articles_df, companies_df = load_sources()

    print(f"Articles loaded: {len(articles_df)}")
    print(f"Companies loaded: {len(companies_df)}")
