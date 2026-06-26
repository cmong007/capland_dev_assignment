"""
schemas.py
----------
Pydantic data models defining the structured output schemas for the
SiteIntel AI extraction engine. These schemas are passed to the Gemini
API to guarantee typed, structured JSON responses.
"""

from pydantic import BaseModel, Field
from typing import Optional


class Transaction(BaseModel):
    """A single comparable property transaction."""
    property_name: str = Field(description="Name or address of the property")
    transaction_date: Optional[str] = Field(None, description="Date of transaction in YYYY-MM or YYYY-MM-DD format")
    size_sqft: Optional[float] = Field(None, description="Size in square feet")
    size_sqm: Optional[float] = Field(None, description="Size in square metres")
    price_local_currency: Optional[float] = Field(None, description="Total transaction price in local currency")
    currency: str = Field(description="3-letter ISO currency code, e.g. SGD, THB, USD")
    price_usd_equivalent: Optional[float] = Field(None, description="Estimated USD equivalent at approximate exchange rate")
    price_psf: Optional[float] = Field(None, description="Price per square foot in local currency")
    price_psm: Optional[float] = Field(None, description="Price per square metre in local currency")
    property_type: str = Field(description="Type: residential / commercial / retail / industrial / mixed-use")
    tenure: Optional[str] = Field(None, description="Freehold / 99-year leasehold / etc.")
    notes: Optional[str] = Field(None, description="Any additional context about this transaction")


class TransactionList(BaseModel):
    """A list of extracted comparable transactions."""
    transactions: list[Transaction]
    source_location: str = Field(description="The general area or market these transactions relate to")


class ZoningSummary(BaseModel):
    """Zoning and regulatory summary for a site or district."""
    location: str = Field(description="Name of the site, district, or planning area")
    zoning_code: Optional[str] = Field(None, description="Official zoning classification code")
    permitted_uses: list[str] = Field(default_factory=list, description="List of permitted land uses")
    prohibited_uses: list[str] = Field(default_factory=list, description="List of prohibited land uses")
    max_plot_ratio: Optional[float] = Field(None, description="Maximum permissible plot ratio (GFA/Site Area)")
    max_height_storeys: Optional[int] = Field(None, description="Maximum building height in storeys")
    max_height_metres: Optional[float] = Field(None, description="Maximum building height in metres")
    key_restrictions: list[str] = Field(default_factory=list, description="Other notable planning restrictions or requirements")
    source_document: Optional[str] = Field(None, description="Name or type of source document")


class PipelineProject(BaseModel):
    """A competitor or upcoming development project in the pipeline."""
    project_name: str = Field(description="Name of the development project")
    developer: Optional[str] = Field(None, description="Developer or owner name")
    sector: str = Field(description="Sector: residential / commercial / retail / mixed-use / industrial")
    estimated_units: Optional[int] = Field(None, description="Number of residential units if applicable")
    estimated_nla_sqm: Optional[float] = Field(None, description="Net lettable area in sqm for commercial projects")
    completion_year: Optional[int] = Field(None, description="Expected completion year")
    status: Optional[str] = Field(None, description="Status: planned / under construction / completed")
    distance_from_site: Optional[str] = Field(None, description="Approximate distance from the subject site")
    notes: Optional[str] = Field(None, description="Additional context")


class PipelineList(BaseModel):
    """A list of extracted pipeline/competitor projects."""
    projects: list[PipelineProject]


class MarketContext(BaseModel):
    """Demographic and macro market context for the subject area."""
    location: str = Field(description="Planning area, district, or city")
    population: Optional[int] = Field(None, description="Total population")
    population_year: Optional[int] = Field(None, description="Year the population figure relates to")
    population_growth_pct: Optional[float] = Field(None, description="Annual population growth rate as a percentage")
    median_household_income: Optional[float] = Field(None, description="Median monthly household income")
    income_currency: Optional[str] = Field(None, description="Currency of the income figure")
    income_growth_pct: Optional[float] = Field(None, description="Annual income growth rate as a percentage")
    key_drivers: list[str] = Field(default_factory=list, description="Key economic or planning drivers for the area")
    transit_highlights: list[str] = Field(default_factory=list, description="Notable transit infrastructure or access points")


class ExtractionResult(BaseModel):
    """The complete structured extraction result for a site assessment."""
    site_name: str
    transactions: TransactionList
    zoning: Optional[ZoningSummary] = None
    pipeline: Optional[PipelineList] = None
    market_context: Optional[MarketContext] = None


# ── Golden Record Pipeline Architecture Models ────────────────────────────────

class LegalConstraints(BaseModel):
    """Zoning and planning parameters extracted from planning/tender documents."""
    gross_plot_ratio: Optional[float] = Field(
        None, 
        description="Maximum permissible gross plot ratio under the URA Master Plan."
    )
    max_allowable_height: Optional[int] = Field(
        None, 
        description="Maximum allowable building height in storeys."
    )
    special_conditions: list[str] = Field(
        default_factory=list, 
        description="List of specific planning conditions, easements, or MRT linkway requirements."
    )


class SupplyThreats(BaseModel):
    """Regional supply statistics calculated from competitor pipeline databases."""
    nearby_uncompleted_units: Optional[int] = Field(
        None, 
        description="Total count of upcoming competitor units in the planning district pipeline."
    )
    expected_completion_window: Optional[str] = Field(
        None, 
        description="Aggregated expected completion timeline window (e.g. '2026-2028')."
    )


class ValuationComparables(BaseModel):
    """Comparable pricing benchmarks computed from transaction caveated sales."""
    median_historical_psf: Optional[float] = Field(
        None, 
        description="Median historical sales price in SGD PSF across analyzed transactions."
    )
    transaction_count_analyzed: Optional[int] = Field(
        None, 
        description="Total number of historical caveated transaction records analyzed."
    )


class ProjectConcentration(BaseModel):
    """Detailed pricing for a single comparable project in the catchment."""
    project_name: str = Field(description="Comparable project name.")
    count: int = Field(description="Number of transaction records.")
    average_psf: float = Field(description="Average pricing in SGD PSF.")


class QuarterlyTrend(BaseModel):
    """catchment volume and price trajectory aggregated by calendar quarter."""
    quarter: str = Field(description="Quarter label (e.g. 'Q1 2024').")
    volume: int = Field(description="Total transaction volume count.")
    average_psf: float = Field(description="Average transaction price in SGD PSF.")


class FloorPremium(BaseModel):
    """catchment pricing stats aggregated by storey groups."""
    floor_range: str = Field(description="Storey range band (e.g. '01-05').")
    count: int = Field(description="Transaction count in this band.")
    average_psf: float = Field(description="Average pricing in SGD PSF.")


class MarketAnalyticsStats(BaseModel):
    """Catchment market analytics metrics computed from transaction data."""
    average_psf: Optional[float] = Field(None, description="Average transaction price in SGD PSF.")
    min_psf: Optional[float] = Field(None, description="Minimum transaction price in SGD PSF.")
    max_psf: Optional[float] = Field(None, description="Maximum transaction price in SGD PSF.")
    new_sale_percent: Optional[float] = Field(None, description="Percentage of transactions that are new sales.")
    average_age: Optional[float] = Field(None, description="Average building age of comparable developments in years.")
    most_active_project: Optional[str] = Field(None, description="Comparable project with the highest transaction volume in the catchment.")
    project_concentrations: Optional[list[ProjectConcentration]] = Field(default_factory=list, description="Historical comp projects in the catchment.")
    quarterly_trends: Optional[list[QuarterlyTrend]] = Field(default_factory=list, description="Quarter-by-quarter volume and pricing history.")
    floor_premiums: Optional[list[FloorPremium]] = Field(default_factory=list, description="Pricing distribution by storey bands.")


class UnderwritingFinancials(BaseModel):
    """Residual land valuation model calculations for proposal pricing."""
    target_launch_psf: float = Field(description="Underwritten target sale price per sqft.")
    breakeven_psf: float = Field(description="Underwritten development breakeven price per sqft.")
    efficiency_ratio: float = Field(default=0.85, description="Net Saleable Area to Gross Floor Area efficiency ratio.")
    estimated_gdv_sgd: float = Field(description="Estimated Gross Development Value in SGD (Max GFA * Efficiency * Target Launch PSF).")
    estimated_construction_cost_sgd: float = Field(description="Estimated Construction cost in SGD.")
    estimated_tdc_sgd: float = Field(description="Estimated Total Development Cost in SGD (Construction + Professional Fees + Finance + Marketing).")
    target_profit_sgd: float = Field(description="Developer target profit margin in SGD (15% of GDV).")
    residual_land_value_sgd: float = Field(description="Residual land bid value in SGD (GDV - TDC - Profit).")
    residual_land_value_psf_ppr: float = Field(description="Residual land bid value per square foot of plot ratio (PSF PPR).")


class GoldenRecord(BaseModel):
    """The single source of truth payload containing normalized real estate parameters."""
    legal_constraints: LegalConstraints = Field(
        ..., 
        description="Legal and planning zoning limits parsed from unstructured texts."
    )
    supply_threats: SupplyThreats = Field(
        ..., 
        description="Precinct-level supply counts and timelines parsed from pipeline databases."
    )
    valuation_comparables: ValuationComparables = Field(
        ..., 
        description="Market comparable PSF benchmarks calculated from historical transaction records."
    )
    market_analytics: Optional[MarketAnalyticsStats] = Field(
        None,
        description="Catchment market analytics metrics computed from transaction data."
    )
    underwriting_financials: Optional[UnderwritingFinancials] = Field(
        None,
        description="Residual land valuation parameters for developer bidding."
    )

