from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1] / "data/output/"

DEFAULT_DB_PATH = PROJECT_ROOT / "tech_news.duckdb"

TABLE_FILES = {
    "dim_company": PROJECT_ROOT / "dim_company.csv",
    "fact_article_arr": PROJECT_ROOT / "fact_article_arr.csv",
    "fact_article_arr_enriched": (
        PROJECT_ROOT / "fact_article_arr_enriched.csv"
    ),
    "ai_articles_enriched": PROJECT_ROOT / "ai_articles_enriched.csv",
}

EXPECTED_TABLES = {
    "dim_company",
    "fact_article_arr",
    "fact_article_arr_enriched",
    "ai_articles_enriched",
}



def get_connection(db_path=DEFAULT_DB_PATH):
    """Open a persisted DuckDB connection."""
    return duckdb.connect(str(db_path))

def validate_duckdb_tables(con, embedding_dimension=384):
    """
    Validate modeled DuckDB tables after loading.

    Raises
    ------
    ValueError
        If any data-quality rule fails.
    """

    # ---------------------------------------------------------
    # 1. Validate expected tables exist
    # ---------------------------------------------------------
    existing_tables = {
        row[0]
        for row in con.execute("SHOW TABLES").fetchall()
    }

    missing_tables = EXPECTED_TABLES - existing_tables

    if missing_tables:
        raise ValueError(
            f"Missing DuckDB tables: {sorted(missing_tables)}"
        )

    # ---------------------------------------------------------
    # 2. dim_company key must be non-null and unique
    # ---------------------------------------------------------
    null_company_count = con.execute("""
        SELECT COUNT(*)
        FROM dim_company
        WHERE company_name IS NULL
    """).fetchone()[0]

    if null_company_count > 0:
        raise ValueError(
            f"dim_company contains {null_company_count} "
            "null company_name values"
        )

    duplicate_company_count = con.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                company_name
            FROM dim_company
            GROUP BY company_name
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    if duplicate_company_count > 0:
        raise ValueError(
            f"dim_company contains {duplicate_company_count} "
            "duplicated company keys"
        )

    # ---------------------------------------------------------
    # 3. fact_article_arr article_id must be non-null and unique
    # ---------------------------------------------------------
    null_article_count = con.execute("""
        SELECT COUNT(*)
        FROM fact_article_arr
        WHERE article_id IS NULL
    """).fetchone()[0]

    if null_article_count > 0:
        raise ValueError(
            f"fact_article_arr contains {null_article_count} "
            "null article_id values"
        )

    duplicate_article_count = con.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                article_id
            FROM fact_article_arr
            GROUP BY article_id
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    if duplicate_article_count > 0:
        raise ValueError(
            f"fact_article_arr contains {duplicate_article_count} "
            "duplicated article IDs"
        )

    # ---------------------------------------------------------
    # 4. Enriched fact should preserve article grain
    # ---------------------------------------------------------
    fact_count = con.execute("""
        SELECT COUNT(*)
        FROM fact_article_arr
    """).fetchone()[0]

    enriched_count = con.execute("""
        SELECT COUNT(*)
        FROM fact_article_arr_enriched
    """).fetchone()[0]

    if fact_count != enriched_count:
        raise ValueError(
            "Row-count mismatch between fact_article_arr "
            "and fact_article_arr_enriched: "
            f"{fact_count} vs {enriched_count}"
        )

    duplicate_enriched_count = con.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                article_id
            FROM fact_article_arr_enriched
            GROUP BY article_id
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    if duplicate_enriched_count > 0:
        raise ValueError(
            "fact_article_arr_enriched contains "
            f"{duplicate_enriched_count} duplicated article IDs"
        )

    # ---------------------------------------------------------
    # 5. ARR values must be positive when present
    # ---------------------------------------------------------
    invalid_arr_count = con.execute("""
        SELECT COUNT(*)
        FROM fact_article_arr_enriched
        WHERE arr_usd IS NOT NULL
          AND arr_usd <= 0
    """).fetchone()[0]

    if invalid_arr_count > 0:
        raise ValueError(
            f"Found {invalid_arr_count} invalid ARR values"
        )

    # ---------------------------------------------------------
    # 6. Embedding length must match expected dimension
    # ---------------------------------------------------------
    invalid_embedding_count = con.execute(f"""
        SELECT COUNT(*)
        FROM fact_article_arr_enriched
        WHERE embedding IS NULL
           OR array_length(embedding) <> {embedding_dimension}
    """).fetchone()[0]

    if invalid_embedding_count > 0:
        raise ValueError(
            f"Found {invalid_embedding_count} embeddings "
            f"with invalid dimension"
        )

    # ---------------------------------------------------------
    # 7. AI export business rules
    # ---------------------------------------------------------
    invalid_ai_category_count = con.execute("""
        SELECT COUNT(*)
        FROM ai_articles_enriched
        WHERE NOT (
            category = 'AI_ML'
            OR industry = 'AI/ML'
        )
    """).fetchone()[0]

    if invalid_ai_category_count > 0:
        raise ValueError(
            "ai_articles_enriched contains "
            f"{invalid_ai_category_count} non-AI records"
        )

    invalid_ai_date_count = con.execute("""
        SELECT COUNT(*)
        FROM ai_articles_enriched
        WHERE published_date < TIMESTAMPTZ '2022-01-01'
           OR published_date >= TIMESTAMPTZ '2025-01-01'
    """).fetchone()[0]

    if invalid_ai_date_count > 0:
        raise ValueError(
            "ai_articles_enriched contains "
            f"{invalid_ai_date_count} records outside 2022-2024"
        )

    invalid_ai_arr_count = con.execute("""
        SELECT COUNT(*)
        FROM ai_articles_enriched
        WHERE arr_usd IS NULL
           OR arr_usd <= 50000000
    """).fetchone()[0]

    if invalid_ai_arr_count > 0:
        raise ValueError(
            "ai_articles_enriched contains "
            f"{invalid_ai_arr_count} records with invalid ARR"
        )

    print("DuckDB validations passed.")


def load_tables_to_duckdb(
    con,
    table_files=None,
    embedding_dimension=384,
):
    """
    Load modeled CSV outputs into DuckDB.

    Embedding CSV values are expected to be valid JSON arrays.
    """
    table_files = table_files or TABLE_FILES

    for table_name, file_path in table_files.items():
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"CSV not found for {table_name}: {file_path}"
            )

        if table_name in {
            "fact_article_arr_enriched",
            "ai_articles_enriched",
        }:
            con.execute(
                f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT
                    * EXCLUDE (embedding),
                    embedding::JSON::FLOAT[{embedding_dimension}]
                        AS embedding
                FROM read_csv_auto(?)
                """,
                [str(file_path)],
            )
        else:
            con.execute(
                f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT *
                FROM read_csv_auto(?)
                """,
                [str(file_path)],
            )

    validate_duckdb_tables(
            con,
            embedding_dimension=embedding_dimension,
        )   

def hybrid_search(
    query_text,
    con,
    embedding_model,
    top_k=5,
    start_date="2022-01-01",
    end_date="2025-01-01",
    min_arr=50_000_000,
    embedding_dimension=384,
):
    """
    Hybrid article search using SQL filters and cosine similarity.
    """

    query_embedding = embedding_model.encode(
        query_text
    )

    query_embedding = [
        float(value)
        for value in query_embedding
    ]

    sql = f"""
        SELECT
            article_id,
            title,
            company_name_resolved,
            published_date_clean,
            category_clean,
            industry,
            arr_usd,

            array_cosine_similarity(
                embedding,
                ?::FLOAT[{embedding_dimension}]
            ) AS similarity_score

        FROM fact_article_arr_enriched

        WHERE (
            category_clean = 'AI_ML'
            OR industry = 'AI/ML'
        )

        AND published_date_clean >= ?::TIMESTAMPTZ
        AND published_date_clean < ?::TIMESTAMPTZ

        AND arr_usd IS NOT NULL
        AND arr_usd > ?

        ORDER BY similarity_score DESC

        LIMIT ?
    """

    return con.execute(
        sql,
        [
            query_embedding,
            start_date,
            end_date,
            min_arr,
            top_k,
        ],
    ).df()

def run_hybrid_search_example(
    con,
    embedding_model,
):
    """
    Example hybrid search required by the assignment.

    Finds AI-related articles published between 2022 and 2024,
    with ARR greater than $50M, ranked by semantic similarity
    to a natural-language query.
    """

    query_text = (
        "companies building generative AI infrastructure"
    )

    results = hybrid_search(
        query_text=query_text,
        con=con,
        embedding_model=embedding_model,
        top_k=5,
        start_date="2022-01-01",
        end_date="2025-01-01",
        min_arr=50_000_000,
    )

    print("\nHybrid search example")
    print("---------------------")
    print(f"Query: {query_text}")
    print(
        "Filters: AI-related, 2022-2024, ARR > $50M"
    )
    print()

    print(results)

    return results


if __name__ == "__main__":

    from semantic_search import load_embedding_model

    con = get_connection()

    try:
        # -----------------------------------------
        # Load modeled CSVs into DuckDB
        # -----------------------------------------
        load_tables_to_duckdb(con)

        print("\nLoaded DuckDB tables:")
        print(
            con.sql(
                "SHOW TABLES"
            ).df()
        )

        # -----------------------------------------
        # Load embedding model
        # -----------------------------------------
        print("\nLoading embedding model...")

        embedding_model = (
            load_embedding_model()
        )

        # -----------------------------------------
        # Run hybrid search example
        # -----------------------------------------
        run_hybrid_search_example(
            con=con,
            embedding_model=embedding_model,
        )

    finally:
        con.close()
