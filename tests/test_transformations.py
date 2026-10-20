import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform import (
    derive_company_age,
    derive_company_size,
    normalize_category,
    parse_arr_usd,
    parse_published_date,
    resolve_company_name,
)


def test_parse_arr_usd_usd_billions():
    assert parse_arr_usd("$5.2B") == 5_200_000_000


def test_parse_arr_usd_range_midpoint():
    assert parse_arr_usd("$10M - $20M") == 15_000_000


def test_parse_arr_usd_eur():
    assert parse_arr_usd("€2.1B") == 2_310_000_000


def test_parse_arr_usd_missing():
    assert parse_arr_usd("Not disclosed") is None


def test_parse_published_date_iso():
    value = parse_published_date("2024-09-06")
    assert value == pd.Timestamp("2024-09-06", tz="UTC")


def test_normalize_ai_category():
    assert normalize_category("AI & ML") == "AI_ML"
    assert normalize_category("Machine Learning") == "AI_ML"


def test_company_size_boundaries():
    assert derive_company_size(9_999) == "SMALL"
    assert derive_company_size(10_000) == "MEDIUM"
    assert derive_company_size(30_000) == "MEDIUM"
    assert derive_company_size(30_001) == "LARGE"


def test_company_age():
    assert (
        derive_company_age(
            2012,
            pd.Timestamp("2024-06-15", tz="UTC"),
        )
        == 12
    )


def test_company_alias_resolution():
    canonical = [
        "Amazon Web Services",
        "OpenAI",
        "NVIDIA",
    ]

    assert (
        resolve_company_name("AWS", canonical)
        == "Amazon Web Services"
    )
