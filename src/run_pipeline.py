from pathlib import Path

from ingest import load_sources
from transform import (
    build_ai_articles_enriched,
    build_dim_company,
    build_fact_article_arr,
    build_fact_article_arr_enriched,
)
from semantic_search import (
    add_embeddings,
    load_embedding_model,
)
from validations import validate_all
from duckdb_load import (
    get_connection,
    load_tables_to_duckdb,
)



PROJECT_ROOT = Path(__file__).resolve().parents[1]


def export_outputs(
    dim_company,
    fact_article_arr,
    fact_article_arr_enriched,
    ai_articles_enriched,
    output_dir=PROJECT_ROOT,
):
    """
    Export all required modeled CSVs.

    For the enriched fact, the in-memory NumPy embedding is replaced
    by its valid JSON serialization before CSV export.
    """
    output_dir = Path(output_dir / "data/output/")
    output_dir.mkdir(parents=True, exist_ok=True)

    dim_company.to_csv(
        output_dir / "dim_company.csv",
        index=False,
    )

    fact_article_arr.to_csv(
        output_dir / "fact_article_arr.csv",
        index=False,
    )

    enriched_export = fact_article_arr_enriched.copy(deep=True)

    enriched_export["embedding"] = (
        enriched_export["embedding_serialized"]
    )

    enriched_export = enriched_export.drop(
        columns=["embedding_serialized"],
        errors="ignore",
    )

    fact_article_arr_enriched_path = (
        output_dir / "fact_article_arr_enriched.csv"
    )

    enriched_export.to_csv(
        fact_article_arr_enriched_path,
        index=False,
    )

    ai_articles_enriched.to_csv(
        output_dir / "ai_articles_enriched.csv",
        index=False,
    )

def run_pipeline(load_duckdb=True):
    """
    Run the full local pipeline in a single Python process.

    DataFrames are passed from one stage to the next in memory.
    No module needs to rely on notebook state.
    """
    print("1. Loading source data...")
    articles_df, companies_df = load_sources()

    print("2. Building company dimension...")
    dim_company = build_dim_company(companies_df)

    print("3. Building article ARR fact...")
    fact_article_arr = build_fact_article_arr(
        articles_df,
        dim_company,
    )

    print("4. Enriching article ARR fact...")
    fact_article_arr_enriched = (
        build_fact_article_arr_enriched(
            fact_article_arr,
            dim_company,
        )
    )

    print("5. Generating article embeddings...")
    embedding_model = load_embedding_model()

    fact_article_arr_enriched = add_embeddings(
        fact_article_arr_enriched,
        embedding_model=embedding_model,
    )

    print("6. Building required AI export...")
    ai_articles_enriched = build_ai_articles_enriched(
        fact_article_arr_enriched
    )

    print("7. Running data validations...")
    validate_all(
        dim_company,
        fact_article_arr,
        fact_article_arr_enriched,
        ai_articles_enriched,
    )

    print("8. Exporting CSV outputs...")
    export_outputs(
        dim_company,
        fact_article_arr,
        fact_article_arr_enriched,
        ai_articles_enriched,
    )

    if load_duckdb:
        print("9. Loading outputs into DuckDB...")
        con = get_connection()

        try:
            load_tables_to_duckdb(con)
        finally:
            con.close()                

    print("Pipeline completed successfully.")

    return {
        "dim_company": dim_company,
        "fact_article_arr": fact_article_arr,
        "fact_article_arr_enriched": (
            fact_article_arr_enriched
        ),
        "ai_articles_enriched": ai_articles_enriched,
    }


if __name__ == "__main__":
    run_pipeline()
