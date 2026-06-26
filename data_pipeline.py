"""
data_pipeline.py
----------------
Ingestion Pipeline mapping structured and unstructured data to a single GoldenRecord.
- Structured Path: Ingests transaction list and competitor database to populate comparables and supply slots.
- Unstructured Path (Extraction Agent): Uses Gemini structure-extraction to parse LegalConstraints from planning text.
"""

import os
import re
import pandas as pd
import streamlit as st
from typing import List, Optional, Dict, Any

from schemas import GoldenRecord, LegalConstraints, SupplyThreats, ValuationComparables, MarketAnalyticsStats, ProjectConcentration, QuarterlyTrend, FloorPremium, UnderwritingFinancials
from geospatial import geocode_onemap, filter_transactions_by_proximity, filter_pipeline_by_proximity, GLS_SITES_COORDS

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LIVE_MODE = bool(GEMINI_API_KEY)

if LIVE_MODE:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    MODEL = "gemini-2.5-flash"

# ── Pipeline Supply Database by District ──────────────────────────────────────
PIPELINE_DATABASE: Dict[str, List[Dict[str, Any]]] = {
    "1": [
        {"project_name": "Marina Gardens Residences", "estimated_units": 790, "completion_year": 2028},
    ],
    "5": [
        {"project_name": "The Hill @ One-North", "estimated_units": 142, "completion_year": 2026},
        {"project_name": "Blossoms By The Park", "estimated_units": 275, "completion_year": 2026},
        {"project_name": "Media Circle Residences", "estimated_units": 355, "completion_year": 2027},
    ],
    "15": [
        {"project_name": "Grand Dunman", "estimated_units": 1008, "completion_year": 2028},
        {"project_name": "Tembusu Grand", "estimated_units": 638, "completion_year": 2027},
    ],
    "18": [
        {"project_name": "Tampines Ave 11 Mixed Use", "estimated_units": 1190, "completion_year": 2029},
        {"project_name": "Tenet (EC)", "estimated_units": 618, "completion_year": 2026},
    ],
    "20": [
        {"project_name": "Lentor Hills Residences", "estimated_units": 476, "completion_year": 2027},
        {"project_name": "Lentor Mansion", "estimated_units": 533, "completion_year": 2028},
        {"project_name": "Lentoria", "estimated_units": 267, "completion_year": 2027},
    ],
    "22": [
        {"project_name": "Sora", "estimated_units": 440, "completion_year": 2028},
        {"project_name": "Luminar Grand (EC)", "estimated_units": 512, "completion_year": 2028},
        {"project_name": "The Lakegarden Residences", "estimated_units": 306, "completion_year": 2027},
        {"project_name": "J'Den", "estimated_units": 368, "completion_year": 2028},
    ],
    "23": [
        {"project_name": "Hillock Green", "estimated_units": 485, "completion_year": 2027},
        {"project_name": "The Myst", "estimated_units": 408, "completion_year": 2027},
    ],
}

SYSTEM_PROMPT_EXTRACTION = """
You are a senior regulatory and planning data extractor. Your sole job is to 
analyze the raw unstructured planning documents or tender packet excerpts and 
extract specific planning parameters.

Rules:
- Extract gross_plot_ratio (float value, e.g., 2.8 or 4.2).
- Extract max_allowable_height (integer storey count, e.g., 24 or 40).
- Extract special_conditions (list of strings representing key planning directives, e.g., "MRT connection required", "15% green coverage").
- Base all extractions strictly on the provided text.
- If a parameter is not explicitly mentioned, return null. Do not invent or infer anything.
"""

# ── Extraction Agent (Unstructured Path) ──────────────────────────────────────

@st.cache_data
def extract_legal_constraints(
    unstructured_text: str,
    llm_provider: str = "Gemini (Cloud)",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3"
) -> LegalConstraints:
    """Uses LLM structured extraction to parse LegalConstraints from raw planning text."""
    if not unstructured_text or not unstructured_text.strip():
        return LegalConstraints(gross_plot_ratio=None, max_allowable_height=None, special_conditions=[])

    def _local_parse(text: str) -> LegalConstraints:
        text_lower = text.lower()
        pr = None
        height = None
        conds = []

        # Extrapolate plot ratio
        pr_match = re.search(r"(?:plot ratio|ratio|pr)\s*(?:of|is|limit)?\s*([0-9.]+)", text_lower)
        if pr_match:
            try:
                pr = float(pr_match.group(1))
            except ValueError:
                pass
        
        # Extrapolate height limits
        height_match = re.search(r"([0-9]+)\s*(?:storey|storeys|floors|floor)", text_lower)
        if height_match:
            try:
                height = int(height_match.group(1))
            except ValueError:
                pass

        # Extrapolate special conditions
        if "green" in text_lower or "landscape" in text_lower:
            conds.append("Minimum green provision/landscape index required.")
        if "mrt" in text_lower or "linkway" in text_lower or "transit" in text_lower:
            conds.append("Direct connection to MRT transport network required.")
        if "setback" in text_lower:
            conds.append("Road setbacks must comply with surrounding low-density boundaries.")

        return LegalConstraints(
            gross_plot_ratio=pr,
            max_allowable_height=height,
            special_conditions=conds
        )

    if llm_provider == "Ollama (Local)":
        import requests
        import json
        url = ollama_url.rstrip("/") + "/api/generate"
        system_prompt = SYSTEM_PROMPT_EXTRACTION + "\n\nYou MUST return a valid JSON object matching this schema exactly:\n{\n  \"gross_plot_ratio\": float or null,\n  \"max_allowable_height\": integer or null,\n  \"special_conditions\": [string]\n}"
        prompt = f"Parse constraints from the following text:\n\n{unstructured_text}"
        try:
            resp = requests.post(url, json={
                "model": ollama_model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1}
            }, timeout=30)
            resp.raise_for_status()
            res_text = resp.json().get("response", "")
            data = json.loads(res_text)
            
            sc = data.get("special_conditions", [])
            if not isinstance(sc, list):
                sc = [str(sc)] if sc is not None else []
            else:
                sc = [str(item) for item in sc]
                
            return LegalConstraints(
                gross_plot_ratio=float(data.get("gross_plot_ratio")) if data.get("gross_plot_ratio") is not None else None,
                max_allowable_height=int(data.get("max_allowable_height")) if data.get("max_allowable_height") is not None else None,
                special_conditions=sc
            )
        except Exception as e:
            print(f"Ollama extraction agent warning: {e}. Falling back to default parser.")
            return _local_parse(unstructured_text)

    # Gemini Cloud Route
    if not LIVE_MODE:
        return _local_parse(unstructured_text)

    # Live Gemini API structured output call
    prompt = f"Parse constraints from the following text:\n\n{unstructured_text}"
    try:
        result = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT_EXTRACTION,
                response_mime_type="application/json",
                response_schema=LegalConstraints,
                temperature=0.1,
            )
        )
        return LegalConstraints.model_validate_json(result.text)
    except Exception as e:
        print(f"Extraction agent warning: {e}. Falling back to default parser.")
        # Fallback to local parsing logic on error without recursive api loop
        return _local_parse(unstructured_text)


# ── Golden Record Pipeline Orchestrator ───────────────────────────────────────

def run_viability_pipeline(
    site_details: dict,
    transactions: list[dict],
    unstructured_text: Optional[str] = None,
    proximity_radius_km: Optional[float] = None,
    llm_provider: str = "Gemini (Cloud)",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3"
) -> tuple[GoldenRecord, list[dict], list[dict]]:
    """
    Orchestrates the Golden Record pipeline with optional spatial proximity filtering.
    Normalizes all raw inputs into a single structured JSON (GoldenRecord) source of truth
    and returns the filtered dataset arrays for transparent display.
    """
    district = str(site_details.get("district", "22")).strip()
    site_name = site_details.get("site_name", "")
    
    # ── Resolve selected GLS site coordinates ──
    site_lat, site_lon = None, None
    if site_name in GLS_SITES_COORDS:
        site_lat = GLS_SITES_COORDS[site_name]["lat"]
        site_lon = GLS_SITES_COORDS[site_name]["lon"]
    elif site_details.get("address"):
        site_lat, site_lon = geocode_onemap(site_details["address"])
        
    # ── Apply Spatial Proximity Filters if configured ──
    if site_lat is not None and site_lon is not None:
        filtered_txns = filter_transactions_by_proximity(transactions, site_lat, site_lon, proximity_radius_km)
        db_projects = PIPELINE_DATABASE.get(district, [])
        filtered_supply = filter_pipeline_by_proximity(db_projects, site_lat, site_lon, proximity_radius_km)
    else:
        filtered_txns = transactions
        filtered_supply = PIPELINE_DATABASE.get(district, [])

    # ── Path 1: Structured Valuation Comparables ──────────────────────────────
    median_psf = None
    txn_count = 0
    if filtered_txns:
        df = pd.DataFrame(filtered_txns)
        if not df.empty and "psf" in df.columns:
            df = df.dropna(subset=["psf"])
            if not df.empty:
                median_psf = float(df["psf"].median())
                txn_count = int(len(df))

    val_comps = ValuationComparables(
        median_historical_psf=median_psf,
        transaction_count_analyzed=txn_count
    )

    # ── Path 2: Structured Supply Threats ─────────────────────────────────────
    nearby_units = 0
    comp_years = []

    for p in filtered_supply:
        units = p.get("estimated_units", 0)
        year = p.get("completion_year")
        nearby_units += units
        if year:
            comp_years.append(year)

    if comp_years:
        min_yr = min(comp_years)
        max_yr = max(comp_years)
        window = f"{min_yr}-{max_yr}" if min_yr != max_yr else str(min_yr)
    else:
        window = "Data Insufficient"

    supply_threats = SupplyThreats(
        nearby_uncompleted_units=nearby_units if filtered_supply else 0,
        expected_completion_window=window if filtered_supply else "Data Insufficient"
    )

    # ── Path 3: Unstructured Legal Constraints ────────────────────────────────
    legal_constraints = extract_legal_constraints(
        unstructured_text,
        llm_provider=llm_provider,
        ollama_url=ollama_url,
        ollama_model=ollama_model
    )

    # Fill in catalogue defaults if LLM structured extraction returned null
    if legal_constraints.gross_plot_ratio is None:
        legal_constraints.gross_plot_ratio = site_details.get("plot_ratio")
    if legal_constraints.max_allowable_height is None:
        pr = site_details.get("plot_ratio", 2.8)
        legal_constraints.max_allowable_height = 40 if pr >= 4.0 else (30 if pr >= 2.8 else 24)

    # ── Path 4: Catchment Market Analytics Stats ──────────────────────────────
    avg_psf = None
    min_psf = None
    max_psf = None
    new_sale_percent = None
    avg_age = None
    most_active_project = None
    project_concentrations = []
    quarterly_trends = []
    floor_premiums = []

    if filtered_txns:
        df_tx = pd.DataFrame(filtered_txns)
        if not df_tx.empty and "psf" in df_tx.columns:
            avg_psf = float(df_tx["psf"].mean())
            min_psf = float(df_tx["psf"].min())
            max_psf = float(df_tx["psf"].max())
            
            if "type_of_sale" in df_tx.columns:
                n_sales = df_tx["type_of_sale"].value_counts()
                new_sale_percent = float(n_sales.get("New Sale", 0) / len(df_tx) * 100)
            elif "typeOfSale" in df_tx.columns:
                n_sales = df_tx["typeOfSale"].value_counts()
                new_sale_percent = float(n_sales.get("New Sale", 0) / len(df_tx) * 100)

            if "project" in df_tx.columns:
                from analytics import get_numeric_age
                df_tx["age"] = df_tx.apply(
                    lambda row: get_numeric_age(
                        row.get("project", ""),
                        row.get("type_of_sale", row.get("typeOfSale", ""))
                    ),
                    axis=1
                )
                avg_age = float(df_tx["age"].mean())
                
                proj_counts = df_tx["project"].value_counts()
                if not proj_counts.empty:
                    most_active_project = str(proj_counts.index[0])

                # 1. Project Concentration List
                proj_grp = df_tx.groupby("project").agg(count=("psf", "count"), avg_psf=("psf", "mean")).reset_index()
                for _, r in proj_grp.iterrows():
                    project_concentrations.append(ProjectConcentration(
                        project_name=str(r["project"]),
                        count=int(r["count"]),
                        average_psf=round(float(r["avg_psf"]), 1)
                    ))

            # 2. Quarterly Trends List
            if "quarter" in df_tx.columns:
                def quarter_sort_key(q):
                    try:
                        parts = q.split()
                        return int(parts[1]) * 10 + int(parts[0][1])
                    except Exception:
                        return 0
                q_grp = df_tx.groupby("quarter").agg(volume=("psf", "count"), avg_psf=("psf", "mean")).reset_index()
                q_grp = q_grp.sort_values("quarter", key=lambda s: s.map(quarter_sort_key))
                for _, r in q_grp.iterrows():
                    quarterly_trends.append(QuarterlyTrend(
                        quarter=str(r["quarter"]),
                        volume=int(r["volume"]),
                        average_psf=round(float(r["avg_psf"]), 1)
                    ))

            # 3. Floor Premiums List
            if "floor" in df_tx.columns:
                def floor_order(f):
                    try:
                        return int(str(f).split("-")[0])
                    except Exception:
                        return 0
                fl_grp = df_tx.groupby("floor").agg(count=("psf", "count"), avg_psf=("psf", "mean")).reset_index()
                fl_grp = fl_grp.sort_values("floor", key=lambda s: s.map(floor_order))
                for _, r in fl_grp.iterrows():
                    floor_premiums.append(FloorPremium(
                        floor_range=str(r["floor"]),
                        count=int(r["count"]),
                        average_psf=round(float(r["avg_psf"]), 1)
                    ))

    market_analytics = MarketAnalyticsStats(
        average_psf=avg_psf,
        min_psf=min_psf,
        max_psf=max_psf,
        new_sale_percent=new_sale_percent,
        average_age=avg_age,
        most_active_project=most_active_project,
        project_concentrations=project_concentrations,
        quarterly_trends=quarterly_trends,
        floor_premiums=floor_premiums
    )

    # ── Path 5: Underwriting Financials (Residual Land Valuation) ─────────────
    underwriting_financials = None
    if median_psf is not None:
        prop_type = site_details.get("property_type", "Condominium")
        if "executive" in prop_type.lower():
            target_launch_psf = float(round(median_psf * 1.12, -1))
            breakeven_psf = float(round(target_launch_psf * 0.85, -1))
        else:
            target_launch_psf = float(round(median_psf * 1.15, -1))
            breakeven_psf = float(round(target_launch_psf * 0.82, -1))

        plot_ratio = site_details.get("plot_ratio", 2.8)
        site_area_sqm = site_details.get("site_area_sqm", 10000)
        max_gfa_sqm = site_area_sqm * plot_ratio
        max_gfa_sqft = max_gfa_sqm * 10.764
        efficiency_ratio = 0.85
        
        estimated_gdv_sgd = max_gfa_sqft * efficiency_ratio * target_launch_psf

        est_construction_cost_psf_gfa = 380.0
        estimated_construction_cost_sgd = max_gfa_sqft * est_construction_cost_psf_gfa
        
        professional_fees_sgd = 0.10 * estimated_construction_cost_sgd
        financing_marketing_taxes_sgd = 0.12 * estimated_construction_cost_sgd
        estimated_tdc_sgd = estimated_construction_cost_sgd + professional_fees_sgd + financing_marketing_taxes_sgd
        
        target_profit_sgd = 0.15 * estimated_gdv_sgd
        
        residual_land_value_sgd = estimated_gdv_sgd - estimated_tdc_sgd - target_profit_sgd
        residual_land_value_psf_ppr = residual_land_value_sgd / max_gfa_sqft

        underwriting_financials = UnderwritingFinancials(
            target_launch_psf=target_launch_psf,
            breakeven_psf=breakeven_psf,
            efficiency_ratio=efficiency_ratio,
            estimated_gdv_sgd=estimated_gdv_sgd,
            estimated_construction_cost_sgd=estimated_construction_cost_sgd,
            estimated_tdc_sgd=estimated_tdc_sgd,
            target_profit_sgd=target_profit_sgd,
            residual_land_value_sgd=residual_land_value_sgd,
            residual_land_value_psf_ppr=residual_land_value_psf_ppr
        )

    golden_record = GoldenRecord(
        legal_constraints=legal_constraints,
        supply_threats=supply_threats,
        valuation_comparables=val_comps,
        market_analytics=market_analytics,
        underwriting_financials=underwriting_financials
    )
    
    return golden_record, filtered_txns, filtered_supply
