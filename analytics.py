"""
analytics.py
------------
Calculates market statistics from parsed URA transaction records.
All calculations are plain Python / pandas — no AI involved here.
"""

import pandas as pd
from collections import defaultdict


def calculate_stats(transactions: list[dict]) -> dict:
    """
    Compute key market metrics from a list of transaction records.

    Returns a dict of stats ready to be passed to the AI analyst
    and rendered in the Streamlit dashboard.
    """
    if not transactions:
        return {}

    df = pd.DataFrame(transactions)
    df = df.dropna(subset=["psf", "price_sgd", "size_sqft"])

    if df.empty:
        return {}

    psf_series = df["psf"]

    # ── Core price metrics ────────────────────────────────────────────────────
    stats = {
        "count":         int(len(df)),
        "avg_psf":       round(psf_series.mean(), 0),
        "median_psf":    round(psf_series.median(), 0),
        "min_psf":       round(psf_series.min(), 0),
        "max_psf":       round(psf_series.max(), 0),
        "std_psf":       round(psf_series.std(), 0),
        "avg_price_sgd": round(df["price_sgd"].mean(), 0),
        "avg_size_sqft": round(df["size_sqft"].mean(), 0),
        "avg_size_sqm":  round(df["size_sqm"].mean(), 1),
    }

    # ── Transaction type split ────────────────────────────────────────────────
    if "type_of_sale" in df.columns:
        type_counts = df["type_of_sale"].value_counts()
        stats["new_sale_count"]  = int(type_counts.get("New Sale", 0))
        stats["resale_count"]    = int(type_counts.get("Resale", 0))
        stats["subsale_count"]   = int(type_counts.get("Sub Sale", 0))
        total = stats["count"]
        stats["new_sale_pct"] = round(stats["new_sale_count"] / total * 100, 1) if total else 0

    # ── Quarterly volume trend ────────────────────────────────────────────────
    if "quarter" in df.columns:
        quarterly = (
            df.groupby("quarter")
            .agg(volume=("psf", "count"), avg_psf=("psf", "mean"))
            .reset_index()
        )
        quarterly["avg_psf"] = quarterly["avg_psf"].round(0)
        # Sort by year/quarter
        def quarter_sort_key(q):
            try:
                parts = q.split()
                return int(parts[1]) * 10 + int(parts[0][1])
            except Exception:
                return 0
        quarterly = quarterly.sort_values("quarter", key=lambda s: s.map(quarter_sort_key))
        stats["quarterly"] = quarterly.to_dict("records")

    # ── Floor premium analysis ────────────────────────────────────────────────
    if "floor" in df.columns:
        def floor_order(f):
            try:
                return int(str(f).split("-")[0])
            except Exception:
                return 0

        df["floor_num"] = df["floor"].apply(floor_order)
        floor_stats = (
            df.groupby("floor")
            .agg(avg_psf=("psf", "mean"), count=("psf", "count"))
            .reset_index()
        )
        floor_stats["avg_psf"] = floor_stats["avg_psf"].round(0)
        floor_stats = floor_stats.sort_values(
            "floor", key=lambda s: s.map(lambda f: floor_order(f))
        )
        stats["floor_premium"] = floor_stats.to_dict("records")

    # ── Project-level breakdown ───────────────────────────────────────────────
    if "project" in df.columns:
        project_stats = (
            df.groupby("project")
            .agg(
                count=("psf", "count"),
                avg_psf=("psf", "mean"),
                min_psf=("psf", "min"),
                max_psf=("psf", "max"),
            )
            .reset_index()
            .sort_values("avg_psf", ascending=False)
        )
        for col in ["avg_psf", "min_psf", "max_psf"]:
            project_stats[col] = project_stats[col].round(0)
        stats["by_project"] = project_stats.to_dict("records")

    return stats


# ── Project Completion Lookup — derived from ura_client.PROJECT_DATABASE ────────
# Single source of truth: completion_year=None means BUC; an integer year means completed.

from ura_client import PROJECT_DATABASE as _PROJECT_DATABASE

_COMPLETION_LOOKUP: dict[str, dict] = {
    p["name"].upper(): p for p in _PROJECT_DATABASE
}


def get_completion_year(project_name: str, type_of_sale: str = "") -> str:
    """Helper to resolve a project's completion status or estimated completion year."""
    if not project_name:
        return "Unknown"
    proj_upper = str(project_name).strip().upper()
    entry = _COMPLETION_LOOKUP.get(proj_upper)
    if entry is not None:
        yr = entry.get("completion_year")
        if yr is None:
            return "U/C (Est. 2026-2028)"  # BUC — year not yet known
        return f"Completed ({yr})"

    # Heuristic fallback for projects not in the database
    if type_of_sale == "New Sale":
        return "U/C (Est. 2026-2028)"
    return "Completed (approx. 2010-2020)"


def get_numeric_age(project_name: str, type_of_sale: str = "", current_year: int = 2026) -> int:
    """Helper to resolve a project's age in years (0 for BUC)."""
    if not project_name:
        return 15
    proj_upper = str(project_name).strip().upper()
    entry = _COMPLETION_LOOKUP.get(proj_upper)
    if entry is not None:
        yr = entry.get("completion_year")
        if yr is None:
            return 0  # BUC
        return max(0, current_year - yr)

    # Heuristic fallback for projects not in the database
    if type_of_sale == "New Sale":
        return 0
    return 15  # Default fallback age


def to_dataframe(transactions: list[dict]) -> pd.DataFrame:
    """Return transactions as a clean, display-ready DataFrame."""
    if not transactions:
        return pd.DataFrame()

    df = pd.DataFrame(transactions)
    
    # Inject numeric age column
    if "project" in df.columns:
        df["age"] = df.apply(
            lambda row: get_numeric_age(
                row.get("project", ""),
                row.get("type_of_sale", "")
            ),
            axis=1
        )
        
    display_cols = {
        "project":       "Project",
        "distance_km":   "Distance",
        "age":           "Age (Years)",
        "floor":         "Floor",
        "size_sqft":     "Size (sqft)",
        "size_sqm":      "Size (sqm)",
        "price_sgd":     "Price (SGD)",
        "psf":           "PSF (SGD)",
        "type_of_sale":  "Type of Sale",
        "tenure":        "Tenure",
        "quarter":       "Quarter",
    }
    available = {k: v for k, v in display_cols.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Format numeric columns
    for col in ["Price (SGD)", "PSF (SGD)", "Size (sqft)"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")

    if "Distance" in df.columns:
        df["Distance"] = df["Distance"].apply(lambda x: f"{x:.2f} km" if pd.notna(x) and isinstance(x, (int, float)) else "N/A (Whole District)")

    return df
