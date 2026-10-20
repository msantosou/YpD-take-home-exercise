import json

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_embedding_model(model_name=DEFAULT_MODEL_NAME):
    """Load the sentence-transformer model used by the pipeline."""
    return SentenceTransformer(model_name)


def add_embeddings(
    articles_df,
    embedding_model=None,
    model_name=DEFAULT_MODEL_NAME,
    show_progress_bar=True,
):
    """
    Add embedding_text, embedding, and embedding_serialized columns.

    The in-memory `embedding` column remains a numeric vector.
    `embedding_serialized` is valid JSON for CSV/DuckDB interchange.
    """
    result = articles_df.copy(deep=True)

    if embedding_model is None:
        embedding_model = load_embedding_model(model_name)

    result["embedding_text"] = (
        result["title"].fillna("")
        + " "
        + result["summary"].fillna("")
    ).str.strip()

    embeddings = embedding_model.encode(
        result["embedding_text"].tolist(),
        show_progress_bar=show_progress_bar,
    )

    result["embedding"] = list(embeddings)

    result["embedding_serialized"] = (
        result["embedding"]
        .apply(lambda vector: json.dumps(vector.tolist()))
    )

    return result


def cosine_similarity(vector_a, vector_b):
    """Calculate cosine similarity between two numeric vectors."""
    vector_a = np.asarray(vector_a)
    vector_b = np.asarray(vector_b)

    denominator = (
        np.linalg.norm(vector_a)
        * np.linalg.norm(vector_b)
    )

    if denominator == 0:
        return 0.0

    return float(np.dot(vector_a, vector_b) / denominator)


def find_similar_articles(
    query_text,
    articles_df,
    embedding_model,
    top_k=5,
):
    """Return the top-K semantically similar articles."""
    query_embedding = embedding_model.encode(query_text)

    columns = [
        "article_id",
        "title",
        "company_name",
        "published_date_clean",
        "embedding",
    ]

    available_columns = [
        column
        for column in columns
        if column in articles_df.columns
    ]

    results = articles_df[available_columns].copy()

    results["similarity_score"] = (
        articles_df["embedding"]
        .apply(
            lambda article_embedding: cosine_similarity(
                query_embedding,
                article_embedding,
            )
        )
    )

    return (
        results
        .sort_values("similarity_score", ascending=False)
        .head(top_k)
        .drop(columns=["embedding"], errors="ignore")
    )
