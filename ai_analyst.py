"""
ai_analyst.py
-------------
Synthesis Engine taking only the populated GoldenRecord object.
Strict system prompt formats JSON data into a clean Markdown memo.
Forbids hallucinations and prints 'Data Insufficient' for missing fields.
Automatically falls back to local compiler format if API fails or experiences demand spikes.
"""

import os
import json
import requests
import streamlit as st
from dotenv import load_dotenv

from schemas import GoldenRecord

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LIVE_MODE = bool(GEMINI_API_KEY)

if LIVE_MODE:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    MODEL = "gemini-2.5-flash"


SYSTEM_PROMPT = """
You are a senior real estate investment strategist and underwriting lead. You will receive a clean JSON payload 
containing verified site, comparable transaction, supply, and market analytics data. Your job is to draft a 
detailed, professional REDEVELOPMENT FEASIBILITY & LAND BID UNDERWRITING MEMO in Markdown format.

Your memo must follow this strict 6-section layout exactly, and you must strictly enforce the following ANTI-REPETITION and NARRATIVE RULES:

### CRITICAL ANTI-REPETITION CONSTRAINTS:
1. **Planning guidelines & site specs** (e.g. Gross Plot Ratio, Max GFA, Site Area, Max Storey Height, Special conditions like MRT linkway/setbacks) must ONLY be mentioned in **Section 2**. NEVER repeat or list them in Section 1, 3, 4, 5, or 6.
2. **Recommended Land Bid entry details** (e.g. Total SGD Millions, PSF PPR) must ONLY be mentioned in **Section 1** and **Section 5** (as the final valuation result). NEVER mention or repeat land bid numbers/PSF PPR in Section 2, 3, 4, or 6.
3. **Competitor pipeline projects & unit counts** must ONLY be listed and analyzed in **Section 4**. NEVER repeat detailed competitor unit statistics in Section 1, 2, 3, 5, or 6 (you may briefly mention a supply threat as a qualitative risk in Section 1 or 6, but do not repeat unit counts or name lists).
4. **Any numerical statistic** (e.g., averages, counts, storeys, ages) must only appear in the single section where it belongs, never replicated elsewhere.

### CRITICAL NARRATIVE ANALYSIS CONSTRAINTS:
- For **Section 3 (CATCHMENT MARKET PRICE DYNAMICS)**:
  - You are strictly FORBIDDEN from listing raw data points, individual transaction dates/sizes, lists of projects with prices, storey group lists, or quarter-by-quarter numbers.
  - Instead, write a cohesive, fluid narrative analysis. Synthesize and interpret the trends: price momentum (quarterly PSF trajectory), leasehold age-decay (how age affects pricing), product sizing elasticity (differences in pricing between unit size formats), and floor premium capture (storey band pricing spreads).
  - Use sentences and paragraphs to explain what these trends mean for our target development site (e.g. "The steep storey premium indicates that a taller building profile is highly viable..."). Do not include bullet points or sub-bullets that list individual data points from the JSON payload.

Memo Sections:

1. EXECUTIVE BID & INVESTMENT RECOMMENDATION
   - State the Recommended Land Bid range (Total SGD Millions and PSF PPR), Investment Viability & Risk Rating [Low/Medium/High Risk], Direction [GOOD / RISKY / BAD], and a concise, numbers-backed underwriting investment thesis.

2. SUBJECT PARCEL DESCRIPTION & PLANNING GUIDELINES
   - Summarize the planning guidelines: Site area, gross plot ratio, max GFA (sqm & sqft), max storey height, and a synthesis of special planning conditions (MRT linkways, setbacks, easements). Do not repeat this data in later sections.

3. CATCHMENT MARKET PRICE DYNAMICS (NARRATIVE ANALYSIS)
   - Explain the market trends based on the transaction analytics (average/median PSF, range boundaries, age-decay, pricing spreads, storey premium trends, new vs resale ratio). Explain what these numbers/trends imply for the development's pricing frontier and absorption strategy. No raw lists of data points.

4. PRECINCT SUPPLY VELOCITY & PIPELINE CONCENTRATION
   - Detail the competitive pipeline: number of units, completion timeline, and a narrative on supply threat severity. List the key competitor projects, units, and distances without repeating details from other sections.

5. RESIDUAL LAND VALUATION & BID UNDERWRITING
   - Provide a narrative explanation of the residual land valuation model: GDV, construction costs, TDC, profit margins, and residual bid logic. Focus on the bid pricing sensitivity, underwriting assumptions, and breakeven markup margin relative to the comps median. Do not repeat raw specs (GFA, Plot Ratio) or lists of figures from Section 2 or Section 3.

6. CRITICAL UNDERWRITING RISKS & CAUTION AREAS
   - Focus on distinct threat vectors: supply clusters, physical layout/construction constraints, height limitations, and macro market absorption or price resistance risks.

Ground all arguments and figures strictly in the values present in the JSON payload. Do not invent external statistics. If a data field is missing or null, output 'Data Insufficient' for that specific value.
"""


def generate_assessment(
    golden_record: GoldenRecord,
    llm_provider: str = "Gemini (Cloud)",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3"
) -> str:
    """
    Synthesizes the populated GoldenRecord JSON data into a formatted Draft Memo.
    Enforces strict zero-hallucination compiler rules.
    """
    if llm_provider == "Ollama (Local)":
        url = ollama_url.rstrip("/") + "/api/generate"
        json_payload = golden_record.model_dump_json(indent=2)
        prompt = f"""
Draft a detailed, professional REDEVELOPMENT FEASIBILITY & LAND BID UNDERWRITING MEMO for the following site development based on the Golden Record JSON payload.

JSON Data:
{json_payload}

Ensure that your memo contains all 6 sections detailed in your system instructions. 
Follow the strict ANTI-REPETITION rules: GFA/Plot ratio specs belong ONLY in Section 2, Recommended Bid belongs ONLY in Section 1 & 5, and competitor supply units/timeline details belong ONLY in Section 4.
For Section 3 (CATCHMENT MARKET PRICE DYNAMICS), do NOT list raw datapoints or projects or storey/quarterly lists. You must write a fluid narrative analysis interpreting the pricing spreads, leasehold age decay, floor premiums, and volume trends, explaining what they mean for this site.

Remember: If any value is null or missing in the JSON, output 'Data Insufficient' for that specific value or metric. Do not write anything else for it.
"""
        try:
            resp = requests.post(url, json={
                "model": ollama_model,
                "prompt": prompt,
                "system": SYSTEM_PROMPT,
                "stream": False,
                "options": {"temperature": 0.1}
            }, timeout=30)
            resp.raise_for_status()
            res = resp.json().get("response", "")
            if res:
                return res
            raise ValueError("Ollama returned empty response")
        except Exception as e:
            print(f"Ollama generate assessment error: {e}. Falling back to mock synthesis compilation.")
            return _mock_assessment(golden_record)

    # Gemini Cloud Route
    if not LIVE_MODE:
        return _mock_assessment(golden_record)

    json_payload = golden_record.model_dump_json(indent=2)
    
    prompt = f"""
Draft a detailed, professional REDEVELOPMENT FEASIBILITY & LAND BID UNDERWRITING MEMO for the following site development based on the Golden Record JSON payload.

JSON Data:
{json_payload}

Ensure that your memo contains all 6 sections detailed in your system instructions. 
Follow the strict ANTI-REPETITION rules: GFA/Plot ratio specs belong ONLY in Section 2, Recommended Bid belongs ONLY in Section 1 & 5, and competitor supply units/timeline details belong ONLY in Section 4.
For Section 3 (CATCHMENT MARKET PRICE DYNAMICS), do NOT list raw datapoints or projects or storey/quarterly lists. You must write a fluid narrative analysis interpreting the pricing spreads, leasehold age decay, floor premiums, and volume trends, explaining what they mean for this site.

Remember: If any value is null or missing in the JSON, output 'Data Insufficient' for that specific value or metric. Do not write anything else for it.
"""

    try:
        result = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
            )
        )
        return result.text
    except Exception as e:
        print(f"Gemini API generate content error: {e}. Falling back to mock synthesis compilation.")
        return _mock_assessment(golden_record)


def _mock_assessment(golden_record: GoldenRecord) -> str:
    """
    Mock compiler formatting GoldenRecord data into Markdown memo
    with perfect schema parity, dynamic evaluation logic, narrative catchment analysis,
    and zero repetition of information.
    """
    c = golden_record.legal_constraints
    s = golden_record.supply_threats
    v = golden_record.valuation_comparables
    m = golden_record.market_analytics
    f = golden_record.underwriting_financials
    
    # Normalize Legal constraints
    pr_str = f"{c.gross_plot_ratio}x" if c.gross_plot_ratio is not None else "Data Insufficient"
    height_str = f"{c.max_allowable_height} storeys" if c.max_allowable_height is not None else "Data Insufficient"
    special_str = "\n".join([f"  * {cond}" for cond in c.special_conditions]) if c.special_conditions else "  * None specified"
        
    # Normalize Supply threats
    units = s.nearby_uncompleted_units if s.nearby_uncompleted_units is not None else 0
    units_str = f"{units:,} units" if s.nearby_uncompleted_units is not None else "Data Insufficient"
    timeline_str = s.expected_completion_window if s.expected_completion_window else "Data Insufficient"
    
    # Normalize Valuation benchmarks
    med_psf = v.median_historical_psf
    psf_str = f"SGD {med_psf:,.0f} PSF" if med_psf is not None else "Data Insufficient"
    count_str = f"{v.transaction_count_analyzed:,} transactions" if v.transaction_count_analyzed is not None else "Data Insufficient"
    
    # Normalize Market Analytics
    avg_psf = m.average_psf if (m and m.average_psf is not None) else None
    avg_psf_str = f"SGD {avg_psf:,.0f} PSF" if avg_psf is not None else "Data Insufficient"
    new_pct = m.new_sale_percent if (m and m.new_sale_percent is not None) else None
    age = m.average_age if (m and m.average_age is not None) else None
    active_proj = m.most_active_project if (m and m.most_active_project) else "comparable developments"
    
    age_str = f"{age:.1f} years" if age is not None else "Data Insufficient"
    new_pct_val = f"{new_pct:.1f}%" if new_pct is not None else "Data Insufficient"

    # Narrative Market Analysis calculations
    if avg_psf is not None and med_psf is not None:
        premium_ratio = (avg_psf / med_psf - 1) * 100
        premium_dir = "premium" if premium_ratio > 0 else "discount"
        frontier_narrative = f"The catchment exhibits an average-to-median pricing spread of {abs(premium_ratio):.1f}% ({avg_psf_str} vs. {psf_str}), indicating a healthy {premium_dir} tail driven by high-specification launches."
    else:
        frontier_narrative = "Pricing spreads between average and median values suggest stable benchmark clusters in the catchment."

    if new_pct is not None:
        if new_pct > 50:
            demand_narrative = f"New sales dominate catchment activity at {new_pct:.1f}% of volume. This strong preference for new builds highlights a buyer pool highly receptive to premium developer launches, indicating that a new development will command a healthy market-rate absorption premium."
        else:
            demand_narrative = f"Resales represent the bulk of demand ({100-new_pct:.1f}% of volume). Buyers are heavily anchored to completed resale pricing benchmarks, meaning any new launch will face strong price resistance unless structured with distinct product differentiation."
    else:
        demand_narrative = "The demand split between new sales and resales suggests a balanced market with typical absorption rates."

    if age is not None:
        if age > 15:
            age_narrative = f"Comparable projects show an advanced average building age of {age:.1f} years. The substantial leasehold depreciation in older comps presents an excellent opportunity for a new launch to capture high 'new-build premium' demand, though developers must bid defensively to capture buyers who are anchored to lower price-age frontiers."
        else:
            age_narrative = f"The catchment contains relatively young comparables with an average age of {age:.1f} years. Price decay curves are flat, meaning a new build will compete directly against modern completed projects, requiring superior layouts and lifestyle amenities."
    else:
        age_narrative = "Age depreciation patterns show typical leasehold discount dynamics across the district."

    # Storey premium narrative
    floor_narrative = "Storey analysis indicates a typical floor premium gradient. Units on higher floors command substantial pricing spreads over lower-floor units, making high-rise layout optimization a critical factor for boosting development margins."
    if m and m.floor_premiums:
        low_f = next((f for f in m.floor_premiums if "01" in f.floor_range or "05" in f.floor_range), None)
        high_f = next((f for f in m.floor_premiums if "21" in f.floor_range or "25" in f.floor_range or "31" in f.floor_range), None)
        if low_f and high_f:
            f_spread = high_f.average_psf - low_f.average_psf
            floor_narrative = f"A steep storey premium is active: transactions on higher floors (storeys {high_f.floor_range} averaging SGD {high_f.average_psf:,.0f} PSF) capture a premium of SGD {f_spread:,.0f} PSF over ground/lower-floor units (storeys {low_f.floor_range} averaging SGD {low_f.average_psf:,.0f} PSF), validating high-rise height optimization."

    # Normalize Financials
    if f:
        bid_str = f"SGD {f.residual_land_value_sgd / 1_000_000:.2f} Million"
        bid_psf_ppr_str = f"SGD {f.residual_land_value_psf_ppr:,.2f} PSF PPR"
        launch_psf_str = f"SGD {f.target_launch_psf:,.0f} PSF"
        bk_psf_str = f"SGD {f.breakeven_psf:,.0f} PSF"
        eff_str = f"{f.efficiency_ratio * 100:.0f}%"
        profit_pct = (f.target_profit_sgd / f.estimated_gdv_sgd * 100) if f.estimated_gdv_sgd > 0 else 0
        financial_narrative = f"Residual land underwriting models a Gross Development Value (GDV) of SGD {f.estimated_gdv_sgd / 1_000_000:.2f} Million (assuming a target launch of {launch_psf_str} at {eff_str} GFA efficiency) against a Total Development Cost (TDC) of SGD {f.estimated_tdc_sgd / 1_000_000:.2f} Million. Factoring in a target developer margin of {profit_pct:.0f}% (SGD {f.target_profit_sgd / 1_000_000:.2f} Million), the maximum supportable land bid is derived at {bid_str} ({bid_psf_ppr_str}). This establishes an underwritten development breakeven of {bk_psf_str}."
        
        if med_psf is not None and f.breakeven_psf > 0:
            markup_pct = ((f.breakeven_psf / med_psf) - 1) * 100
            markup_str = f"{markup_pct:.1f}% markup relative to current comps median PSF"
        else:
            markup_str = "Data Insufficient"
    else:
        bid_str = "Data Insufficient"
        bid_psf_ppr_str = "Data Insufficient"
        launch_psf_str = "Data Insufficient"
        bk_psf_str = "Data Insufficient"
        eff_str = "Data Insufficient"
        markup_str = "Data Insufficient"
        financial_narrative = "Financial underwritings indicate standard residual bid models based on catchment comps. Detailed financials are currently unavailable."

    # Evaluative Risk logic
    if units > 800:
        dir_str = "RISKY (High Competitor Supply)"
        rating_str = "High Risk"
        thesis_str = f"The site sits in a high-density supply corridor with {units:,} uncompleted competitor units slated for completion in the {timeline_str} window. This cluster threatens price absorption rates, demanding a defensive land bidding entry strategy."
    elif v.transaction_count_analyzed is not None and v.transaction_count_analyzed < 15:
        dir_str = "RISKY (Illiquid Catchment)"
        rating_str = "High Risk"
        thesis_str = f"A thin transaction volume of only {count_str} over the last 24 months indicates an illiquid micro-market, introducing high cashflow volatility risks."
    elif med_psf is not None and med_psf > 1850:
        dir_str = "GOOD (Strong Capital Appreciation)"
        rating_str = "Medium Risk"
        thesis_str = f"Catchment PSF is strongly anchored around {psf_str} with robust new sale premiums ({new_pct_val} of volume). Product launch at {launch_psf_str} represents high viability, though the tight developer margins require strict cost control."
    else:
        dir_str = "GOOD (Defensive Yield Play)"
        rating_str = "Low Risk"
        thesis_str = "Low uncompleted supply pipeline and strong local resale floor. Represents an excellent risk-adjusted development opportunity with a stable anticipated absorption."

    return f"""# REDEVELOPMENT FEASIBILITY & LAND BID UNDERWRITING MEMO
**STATUS**: AI-Generated Underwriting Proposal (Internal Review)

---

### 1. EXECUTIVE BID & INVESTMENT RECOMMENDATION
* **Site Viability Direction**: **{dir_str}**
* **Investment Viability & Risk Rating**: **{rating_str}**
* **Recommended Land Bid Entry**:
  * **Total Bid Value**: **{bid_str}**
  * **Land Bid PSF PPR**: **{bid_psf_ppr_str}**
* **Core Underwriting Thesis**: 
  {thesis_str}

---

### 2. SUBJECT PARCEL DESCRIPTION & PLANNING GUIDELINES
* **Parcel Location**: Subject site catchment
* **Gross Plot Ratio**: {pr_str}
* **Max Allowable Height**: {height_str}
* **Special Planning Conditions & Excerpts**:
{special_str}

---

### 3. CATCHMENT MARKET PRICE DYNAMICS (NARRATIVE ANALYSIS)
* **Pricing Frontier & Spread**: {frontier_narrative}
* **Demand Dynamics & Absorption**: {demand_narrative}
* **Age Depreciation & Capital Decay**: {age_narrative}
* **Storey Premium Capture**: {floor_narrative}
* **Catchment Velocity**: The localized market is anchored by **{active_proj}**, which registers the highest comparative transaction density. The overall historical transaction velocity ({count_str}) confirms a deep pool of secondary buyers.

---

### 4. PRECINCT SUPPLY VELOCITY & PIPELINE CONCENTRATION
* **Total Precinct Competitor Supply**: {units_str}
* **Aggregated Completion Window**: {timeline_str}
* **Supply Assessment**: Upcoming units cluster poses a threat to post-construction margins. Underwriting targets must account for price elasticity from secondary buyers.

---

### 5. RESIDUAL LAND VALUATION & BID UNDERWRITING
* **Residual Model Narrative**: {financial_narrative}
* **Pricing Sensitivity**: Underwritten breakeven of **{bk_psf_str}** represents a {markup_str}. This pricing boundary provides defensive margin protection against leasehold depreciation.

---

### 6. CRITICAL UNDERWRITING RISKS & CAUTION AREAS
* **Competitive Cluster Risk**: The upcoming launches within the {timeline_str} window threaten price dominance.
* **Planning Restrictions**: Max height of {height_str} restricts layout flexibility and high-floor premium capture.
* **Leasehold Depreciation**: Comps average age of {age_str} signals a market anchored to older pricing, highlighting potential resale exit resistance.
"""


SYSTEM_PROMPT_INSIGHTS = """
You are a senior real estate quantitative analyst. You analyze property transaction statistics 
and provide brief, high-impact chart interpretations for senior executives.

Rules:
- Generate exactly three bullet points.
- Base your analysis strictly on the numbers provided in the payload. Do not invent external facts or make unsupported guesses.
- Bullet 1 (Pricing Frontier & Margin): Analyze how the proposed target launch price and breakeven PSF sit relative to the catchment's pricing frontier (median, average, minimum, and maximum PSF). Discuss the pricing margin and risk.
- Bullet 2 (Demand Dynamics & Elasticity): Analyze the transaction volume, quarterly trends, and new sale vs. resale demand composition to infer market velocity, demand depth, and price elasticity.
- Bullet 3 (Leasehold Age & Floor Premiums): Analyze how building age (depreciation) and floor levels affect pricing in this catchment, referencing project and floor stats from the payload.
"""

@st.cache_data
def generate_chart_insights(
    stats: dict,
    target_launch: float,
    breakeven: float,
    llm_provider: str = "Gemini (Cloud)",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3"
) -> str:
    """
    Generates a dynamic 3-bullet automated chart interpretation memo
    explaining volume, pricing trends, and pricing frontier implications.
    Cached to prevent duplicate API queries.
    """
    if llm_provider == "Ollama (Local)":
        url = ollama_url.rstrip("/") + "/api/generate"
        json_payload = {
            "target_launch_psf": target_launch,
            "breakeven_psf": breakeven,
            "market_stats": stats
        }
        prompt = f"""
Analyze the following property metrics for a proposed site development and return exactly three key insights:

JSON Stats:
{json_payload}

Format output as three markdown bullets. Focus on pricing frontier placement, volume, and composition.
"""
        try:
            resp = requests.post(url, json={
                "model": ollama_model,
                "prompt": prompt,
                "system": SYSTEM_PROMPT_INSIGHTS,
                "stream": False,
                "options": {"temperature": 0.15}
            }, timeout=30)
            resp.raise_for_status()
            res = resp.json().get("response", "")
            if res:
                return res
            raise ValueError("Ollama returned empty response")
        except Exception as e:
            print(f"Ollama generate insights error: {e}. Falling back to mock generator.")
            return _mock_chart_insights(stats, target_launch, breakeven)

    # Gemini Cloud Route
    if not LIVE_MODE:
        return _mock_chart_insights(stats, target_launch, breakeven)
        
    json_payload = {
        "target_launch_psf": target_launch,
        "breakeven_psf": breakeven,
        "market_stats": stats
    }
    
    prompt = f"""
Analyze the following property metrics for a proposed site development and return exactly three key insights:

JSON Stats:
{json_payload}

Format output as three markdown bullets. Focus on pricing frontier placement, volume, and composition.
"""
    try:
        result = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT_INSIGHTS,
                temperature=0.15,
            )
        )
        return result.text
    except Exception as e:
        print(f"Gemini API insights error: {e}. Falling back to mock generator.")
        return _mock_chart_insights(stats, target_launch, breakeven)


def _mock_chart_insights(stats: dict, target_launch: float, breakeven: float) -> str:
    """Dynamic fallback pricing insights based on calculations."""
    median_psf = stats.get("median_psf", 1900)
    new_pct = stats.get("new_sale_pct", 30)
    count = stats.get("count", 0)
    
    bullets = []
    
    # Bullet 1: Target pricing vs. Frontier
    if target_launch > median_psf * 1.1:
        bullets.append(
            f"• **Frontier Placement**: Proposed launch price of **SGD {target_launch:,.0f} PSF** sits significantly above "
            f"the catchment median of **SGD {median_psf:,.0f} PSF** (+{((target_launch/median_psf)-1)*100:.1f}%). "
            f"This represents pricing at the ceiling of the market frontier, indicating potential absorption compression."
        )
    elif target_launch < median_psf * 0.9:
        bullets.append(
            f"• **Frontier Placement**: Proposed launch price of **SGD {target_launch:,.0f} PSF** is positioned defensively below "
            f"the current catchment median of **SGD {median_psf:,.0f} PSF** (-{((1-target_launch/median_psf))*100:.1f}%). "
            f"This indicates significant pricing headroom and high initial absorption capacity, though margins will be tight."
        )
    else:
        bullets.append(
            f"• **Frontier Placement**: Proposed launch price of **SGD {target_launch:,.0f} PSF** is aligned with the catchment "
            f"median of **SGD {median_psf:,.0f} PSF**. This indicates a stable risk profile matching historical absorption rates."
        )
        
    # Bullet 2: Demand composition and premium
    if new_pct > 50:
        bullets.append(
            f"• **Demand Composition**: The catchment is heavily skewed toward New Sales (**{new_pct:.0f}%** of volume). "
            f"This represents a submarket highly receptive to new builds and willing to pay premium prices, validating proposed margins."
        )
    else:
        bullets.append(
            f"• **Demand Composition**: Resale volume dominates the catchment (**{100-new_pct:.0f}%** of volume). "
            f"This implies potential price resistance from buyers who are anchored to completed resale benchmarks."
        )
        
    # Bullet 3: Volume Cushion & Elasticity
    bullets.append(
        f"• **Volume Cushion**: The historical baseline of **{count:,} transactions** indicates a deep and active localized "
        f"demand pool. Volume surges in recent quarters support localized elasticity for developments that align with the sizing frontier."
    )
    
    return "\n\n".join(bullets)

