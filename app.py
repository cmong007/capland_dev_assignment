"""
app.py
------
GLS Land Parcel Assessor — Streamlit frontend.

A development analyst inputs a GLS site's parameters.
The app fetches real URA comparable transaction data,
calculates market statistics, and uses Gemini AI to
produce a structured market assessment and supportable
land bid estimate.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from dotenv import load_dotenv

from ura_client import get_transactions, load_realis_csv, DISTRICT_MAP, GLS_SITES
from analytics import calculate_stats, to_dataframe
from ai_analyst import generate_assessment, LIVE_MODE
from data_pipeline import run_viability_pipeline

load_dotenv()

# Fetch default settings from .env
ENV_USE_OLLAMA = os.getenv("USE_OLLAMA", "False").strip().lower() == "true"
ENV_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ENV_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GLS Parcel Assessor",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    [data-testid="metric-container"] {
        background: #1E293B; border: 1px solid #334155;
        border-radius: 10px; padding: 16px;
    }
    .section-header {
        font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
        color: #64748B; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .pill-live {
        background: #064E3B; color: #6EE7B7;
        padding: 3px 10px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600; display: inline-block;
    }
    .pill-demo {
        background: #451A03; color: #FCD34D;
        padding: 3px 10px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600; display: inline-block;
    }
    .param-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .param-table td { padding: 6px 12px; border-bottom: 1px solid #1E293B; color: #CBD5E1; }
    .param-table td:first-child {
        color: #64748B; font-size: 0.78rem; text-transform: uppercase;
        letter-spacing: 0.06em; width: 42%;
    }
    .param-table td:last-child { font-weight: 600; color: #F1F5F9; }
    .comp-source {
        background: #0F2235; border-left: 3px solid #2563EB;
        border-radius: 4px; padding: 8px 14px;
        font-size: 0.8rem; color: #93C5FD; margin-bottom: 12px;
    }
    .step-label {
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
        color: #2563EB; text-transform: uppercase; margin-bottom: 2px;
    }
    hr { border-color: #334155 !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

col_title, col_status = st.columns([4, 1])
with col_title:
    st.title("🏗️ Land Parcel Assessor")
    st.caption("Comparable market analysis and land valuation dashboard")
with col_status:
    st.write("")
    st.write("")
    if LIVE_MODE:
        st.markdown('<span class="pill-live">● Live AI Mode</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="pill-demo">● Demo Mode</span>', unsafe_allow_html=True)
        st.caption("Add GEMINI_API_KEY to .env for live analysis")

st.divider()

# Initialize session state for selected site name and map click tracking
_site_labels = [s["name"] for s in GLS_SITES]

# Sync session state keys to prevent drifts between sidebar selectbox and map clicks
if "selected_site_name" not in st.session_state:
    st.session_state["selected_site_name"] = GLS_SITES[0]["name"]

# Sync sidebar dropdown if it has drifted due to map click
if "sidebar_site_select" in st.session_state:
    if st.session_state["sidebar_site_select"] != st.session_state["selected_site_name"]:
        st.session_state["sidebar_site_select"] = st.session_state["selected_site_name"]

if "map_last_clicked" not in st.session_state:
    st.session_state["map_last_clicked"] = None

# ── Sidebar: Site Picker & Configurations ─────────────────────────────────────

with st.sidebar:
    st.markdown("## Land Parcel Assessor")
    st.caption(
        "Select a location or development site to evaluate. "
        "All initial parameters are populated from catalog databases, "
        "and proximity statistics are computed relative to the site centroid."
    )
    st.divider()

    # Step 1: Site Dropdown (Synced with Map Clicks)
    st.markdown('<p class="step-label">&#9312; Select Location</p>', unsafe_allow_html=True)
    
    def on_site_dropdown_change():
        st.session_state["selected_site_name"] = st.session_state["sidebar_site_select"]

    def format_site_name(name):
        s = next((x for x in GLS_SITES if x["name"] == name), None)
        if s and s.get("source_year"):
            return f"D{s['district']} — {name}"
        return name
        
    selected_name = st.selectbox(
        "Location",
        options=_site_labels,
        index=_site_labels.index(st.session_state["selected_site_name"]),
        label_visibility="collapsed",
        help="Sourced from site catalogue database.",
        key="sidebar_site_select",
        on_change=on_site_dropdown_change,
        format_func=format_site_name
    )
    

    
    _site = next(s for s in GLS_SITES if s["name"] == st.session_state["selected_site_name"])
    is_custom = "\U0001F4DD" in selected_name

    if not is_custom:
        _yr = _site.get("source_year", "")
        st.markdown(
            f'<div class="comp-source" style="margin-top:8px;">'
            f'<strong>{_site["address"]}</strong><br>'
            f'Tender: {_yr} &nbsp;|&nbsp; {_site["tenure"]}<br>'
            f'<span style="color:#94A3B8;font-size:0.78rem;">{_site["notes"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        district      = _site["district"]
        site_area_sqm = _site["site_area_sqm"]
        plot_ratio    = _site["plot_ratio"]
        tenure        = _site["tenure"]
        property_type = _site["property_type"]
        permitted_use = _site["permitted_use"]
    else:
        st.markdown('<p class="step-label" style="margin-top:10px;">&#9313; Site Details</p>', unsafe_allow_html=True)
        district = st.selectbox(
            "District",
            options=list(DISTRICT_MAP.keys()),
            format_func=lambda x: f"D{x} \u2014 {DISTRICT_MAP[x]}",
            index=list(DISTRICT_MAP.keys()).index("22"),
        )
        site_area_sqm = st.number_input(
            "Site Area (sqm)",
            min_value=500, max_value=200_000, value=10_000, step=100,
        )
        plot_ratio = st.number_input(
            "Max Plot Ratio",
            min_value=0.5, max_value=25.0, value=2.8, step=0.1,
        )
        tenure = st.selectbox(
            "Tenure",
            ["99-year leasehold", "Freehold", "999-year leasehold"],
        )
        property_type = st.selectbox(
            "Allowable Dwelling Type",
            ["Condominium", "Apartment", "Executive Condominium"],
        )
        permitted_use = st.multiselect(
            "Permitted Uses",
            ["Residential", "Commercial", "Retail", "Hotel", "F&B"],
            default=["Residential"],
        )

    st.divider()

    # Step 2: Unstructured Text
    st.markdown('<p class="step-label">&#9313; Unstructured Planning & Tender Excerpts</p>', unsafe_allow_html=True)
    
    uploaded_pdf = st.file_uploader(
        "Upload planning/tender PDF",
        type=["pdf"],
        help="Extract text from a planning or tender guidelines PDF."
    )
    
    default_notes = _site.get("notes", "") if not is_custom else "Zoned residential-commercial mixed-use site near transport hub."
    
    if uploaded_pdf:
        file_key = f"pdf_text_{uploaded_pdf.name}_{uploaded_pdf.size}"
        if file_key not in st.session_state:
            with st.spinner("Extracting text from PDF..."):
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(uploaded_pdf)
                    pdf_text = ""
                    for page in reader.pages:
                        pdf_text += page.extract_text() or ""
                    st.session_state[file_key] = pdf_text
                    st.session_state["unstructured_raw_excerpts"] = pdf_text
                except Exception as e:
                    st.error(f"Error reading PDF: {e}")
        
        if file_key in st.session_state:
            default_notes = st.session_state[file_key]

    unstructured_input = st.text_area(
        "Raw Excerpts",
        value=default_notes,
        height=100,
        key="unstructured_raw_excerpts",
        label_visibility="collapsed"
    )

    st.divider()

    # Step 3: Data Source
    st.markdown('<p class="step-label">&#9314; Comparable Data Source</p>', unsafe_allow_html=True)
    data_source = st.radio(
        "data_source",
        ["Live URA API (auto)", "Upload URA REALIS CSV"],
        label_visibility="collapsed",
    )

    uploaded_csv = None
    if data_source == "Upload URA REALIS CSV":
        uploaded_csv = st.file_uploader(
            "URA REALIS export (.csv)",
            type=["csv"],
        )

    st.divider()

    # Step 4: Proximity Filter
    st.markdown('<p class="step-label">&#9315; Comparable Proximity Filter</p>', unsafe_allow_html=True)
    proximity_label = st.select_slider(
        "Proximity Filter",
        options=["500m", "1.0 km", "1.5 km", "2.0 km", "3.0 km", "Whole District"],
        value="1.5 km",
        key="proximity_filter_slider",
        label_visibility="collapsed"
    )
    if proximity_label == "500m":
        proximity_radius_km = 0.5
    elif proximity_label == "Whole District":
        proximity_radius_km = None
    else:
        proximity_radius_km = float(proximity_label.replace(" km", "").strip())

    st.divider()
    st.markdown('<p class="step-label">&#9316; AI Model Settings</p>', unsafe_allow_html=True)
    
    llm_options = ["Gemini (Cloud)", "Ollama (Local)"]
    default_idx = 1 if ENV_USE_OLLAMA else 0
    llm_provider = st.selectbox("AI Model Provider", options=llm_options, index=default_idx)
    
    ollama_url = ENV_OLLAMA_HOST
    ollama_model = ENV_OLLAMA_MODEL
    
    if llm_provider == "Ollama (Local)":
        ollama_url = st.text_input("Ollama Host URL", value=ENV_OLLAMA_HOST)
        ollama_model = st.text_input("Ollama Model", value=ENV_OLLAMA_MODEL)
        ai_label = f"Ollama ({ollama_model})"
    else:
        ai_label = "Gemini 2.5 Flash" if LIVE_MODE else "Gemini (Offline Fallback)"
        if not LIVE_MODE:
            st.warning("⚠️ GEMINI_API_KEY not configured in .env. Mock fallback will be used.")
        
    st.caption(f"**Selected AI**: {ai_label}")

# ── Derived Site Metrics & Context ───────────────────────────────────────────

max_gfa_sqm  = site_area_sqm * plot_ratio
max_gfa_sqft = max_gfa_sqm * 10.764

site_details = {
    "site_name":     selected_name if not is_custom else "Custom Site",
    "address":       _site.get("address", "") if not is_custom else "",
    "district":      district,
    "district_name": DISTRICT_MAP.get(district, ""),
    "site_area_sqm": site_area_sqm,
    "plot_ratio":    plot_ratio,
    "max_gfa_sqm":   max_gfa_sqm,
    "tenure":        tenure,
    "property_type": property_type,
    "permitted_use": permitted_use,
    "notes":         _site.get("notes", ""),
}

# Resolve selected site coordinates
from geospatial import geocode_onemap, GLS_SITES_COORDS
site_lat, site_lon = None, None
if site_details["site_name"] in GLS_SITES_COORDS:
    site_lat = GLS_SITES_COORDS[site_details["site_name"]]["lat"]
    site_lon = GLS_SITES_COORDS[site_details["site_name"]]["lon"]
elif site_details.get("address"):
    site_lat, site_lon = geocode_onemap(site_details["address"])

# Reset AI assessment memo if selected site or proximity radius changes
if "last_selected_site" not in st.session_state:
    st.session_state["last_selected_site"] = site_details["site_name"]
    st.session_state["last_proximity"] = proximity_label

if st.session_state["last_selected_site"] != site_details["site_name"] or st.session_state["last_proximity"] != proximity_label:
    if st.session_state["last_selected_site"] != site_details["site_name"]:
        if "unstructured_raw_excerpts" in st.session_state:
            del st.session_state["unstructured_raw_excerpts"]
    st.session_state["last_selected_site"] = site_details["site_name"]
    st.session_state["last_proximity"] = proximity_label
    if "ai_assessment" in st.session_state:
        del st.session_state["ai_assessment"]
    if "edited_memo" in st.session_state:
        del st.session_state["edited_memo"]

# ── Automatically Execute Data Ingestion & Spatial Calculations ────────────────

# Fetch raw transaction records from API or CSV upload
if data_source == "Upload URA REALIS CSV":
    if not uploaded_csv:
        st.info("ℹ️ Upload a URA REALIS CSV file in the sidebar to populate comparable transactions.")
        st.stop()
    all_txns = load_realis_csv(uploaded_csv)
    raw_transactions = []
    for r in all_txns:
        r_dist = str(r.get("district", "")).strip()
        if r_dist != district:
            continue
        t_val = r.get("tenure", "").lower()
        if tenure == "Freehold" and "freehold" not in t_val:
            continue
        if tenure == "99-year leasehold" and "99" not in t_val:
            continue
        p_val = r.get("property_type", "")
        from ura_client import is_comparable_property_type
        if property_type != "All" and not is_comparable_property_type(property_type, p_val):
            continue
        raw_transactions.append(r)
    if not raw_transactions:
        raw_transactions = all_txns
else:
    raw_transactions = get_transactions(district, tenure, property_type)

# Run Golden Record Ingestion pipeline with Proximity Radius Filter
golden_record, filtered_transactions, filtered_supply = run_viability_pipeline(
    site_details=site_details,
    transactions=raw_transactions,
    unstructured_text=unstructured_input,
    proximity_radius_km=proximity_radius_km,
    llm_provider=llm_provider,
    ollama_url=ollama_url,
    ollama_model=ollama_model
)

# Recalculate statistics on spatially filtered comps
stats = calculate_stats(filtered_transactions)
df_display = to_dataframe(filtered_transactions)

# Programmatic residual valuation baseline estimates based on catchment median PSF
_median_val = stats.get("median_psf", 1900) if stats else 1900
if property_type == "Executive Condominium":
    target_launch_psf = float(round(_median_val * 1.12, -1))
    breakeven_psf = float(round(target_launch_psf * 0.85, -1))
else:
    target_launch_psf = float(round(_median_val * 1.15, -1))
    breakeven_psf = float(round(target_launch_psf * 0.82, -1))

comp_source_label = (
    f"CSV upload \u2014 {len(filtered_transactions):,} transactions"
    if data_source == "Upload URA REALIS CSV"
    else f"Live URA API \u2014 {len(filtered_transactions):,} transactions"
)

# ── Interactive Map Dashboard (Neighbors & Proximity Catchment) ───────────────

st.markdown("### 🗺️ Select Location & Analyze Surrounding Market")
st.caption("Click on a marker pin on the map to select a location. The shaded area shows your proximity district catchment. Comps (blue) and competitors (purple) are plotted relative to the site centroid.")

from geospatial import generate_selection_map, geocode_onemap, GLS_SITES_COORDS
from streamlit_folium import st_folium
try:
    fig_map = generate_selection_map(
        GLS_SITES, 
        st.session_state["selected_site_name"],
        comparables=filtered_transactions,
        competitors=filtered_supply,
        radius_km=proximity_radius_km
    )
    map_event = st_folium(
        fig_map,
        width="100%",
        height=550,
        key="gls_site_map",
        returned_objects=["last_object_clicked", "last_clicked"],
    )
    
    # Resolve clicked coordinates from either marker click or raw map click
    _clicked_point = (
        map_event.get("last_object_clicked")
        if map_event and map_event.get("last_object_clicked")
        else (map_event.get("last_clicked") if map_event else None)
    )
    
    if _clicked_point:
        clicked_lat = _clicked_point.get("lat")
        clicked_lon = _clicked_point.get("lng")
        
        # Persist click coordinates across reruns so the selection survives rerun()
        click_key = (round(clicked_lat, 5), round(clicked_lon, 5)) if clicked_lat and clicked_lon else None
        if click_key and click_key != st.session_state.get("map_last_clicked"):
            st.session_state["map_last_clicked"] = click_key
            
            # Find nearest GLS site within 500m tolerance (~0.005 degrees)
            best_site = None
            best_dist = float("inf")
            for site_name, coords in GLS_SITES_COORDS.items():
                dist = abs(coords["lat"] - clicked_lat) + abs(coords["lon"] - clicked_lon)
                if dist < best_dist:
                    best_dist = dist
                    best_site = site_name
            
            # Accept match if within ~500m (0.009 deg ≈ 1km, use 0.005 as threshold)
            if best_site and best_dist < 0.009 and best_site != st.session_state["selected_site_name"]:
                st.session_state["selected_site_name"] = best_site
                st.rerun()
    # Boundary polygon retired to avoid visual clutter and maintain marker consistency
    pass
except Exception as e:
    st.warning(f"Map rendering error: {e}. Fallback to sidebar selection is active.")

st.divider()

# ── Location Parameters & Context ────────────────────────────────────────────

st.markdown('<p class="section-header">Location Parameters & Context</p>', unsafe_allow_html=True)

col_params, col_map = st.columns([3, 2])

with col_params:
    _yr_str = f" ({_site['source_year']} tender)" if _site.get("source_year") else ""
    _param_rows = [
        ("Selected Location", site_details["site_name"] + _yr_str),
        ("Location",       f"District {district} \u2014 {DISTRICT_MAP.get(district, '')}"),
        ("Tenure",         tenure + "  \u00b7  URA-specified"),
        ("Dwelling Type",  property_type + "  \u00b7  URA-zoned"),
        ("Permitted Use",  ", ".join(permitted_use) if permitted_use else "\u2014"),
        ("Site Area",      f"{site_area_sqm:,.0f} sqm"),
        ("Max Plot Ratio", f"{plot_ratio:.1f}\u00d7"),
        ("Max GFA",        f"{max_gfa_sqm:,.0f} sqm  /  {max_gfa_sqft:,.0f} sqft"),
    ]
    _rows_html = "".join(
        f"<tr><td>{lbl}</td><td>{val}</td></tr>" for lbl, val in _param_rows
    )
    st.markdown(
        f'<table class="param-table"><tbody>{_rows_html}</tbody></table>',
        unsafe_allow_html=True,
    )

with col_map:
    # Spatially Filtered Context Card containing proximity statistics & target estimations
    with st.container(border=True):
        st.markdown(f"**🔍 Spatially Filtered Context**")
        st.write(f"Proximity Radius: `{proximity_label}`")
        st.write(f"Comps within Radius: **{len(filtered_transactions)}** / {len(raw_transactions)} (district total)")
        from data_pipeline import PIPELINE_DATABASE
        total_db_supply = len(PIPELINE_DATABASE.get(district, []))
        st.write(f"Competitor projects: **{len(filtered_supply)}** / {total_db_supply} (district total)")
        
        st.markdown("---")
        st.markdown(f"**🎯 Estimated Launch Benchmarks**")
        st.write(f"Est. Target Launch: **SGD {target_launch_psf:,.0f} PSF**")
        st.write(f"Est. Breakeven PSF: **SGD {breakeven_psf:,.0f} PSF**")

st.divider()

# Verify if we have transactions within proximity filter
if not filtered_transactions:
    st.warning("⚠️ No comparable transactions found within the selected proximity radius. Please increase the Proximity Filter in the sidebar or select 'Whole District'.")
    st.stop()

# ── Market Metrics Row ────────────────────────────────────────────────────

st.markdown('<p class="section-header">Market Benchmarks (Filtered Comps)</p>', unsafe_allow_html=True)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Transactions",  f"{stats.get('count', 0):,}")
c2.metric("Avg PSF",       f"SGD {stats.get('avg_psf', 0):,.0f}")
c3.metric("Median PSF",    f"SGD {stats.get('median_psf', 0):,.0f}")
c4.metric("PSF Range",     f"SGD {stats.get('min_psf',0):,.0f} – {stats.get('max_psf',0):,.0f}")
c5.metric("New Sales",     f"{stats.get('new_sale_pct', 0):.0f}%")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "📋 Comparable Transactions",
    "📊 Market Analytics",
    "🤖 AI Assessment & Land Bid",
])

# ── Tab 1: Transactions ───────────────────────────────────────────────────
with tab1:
    st.markdown(
        f'<div class="comp-source">\U0001f4e1 <strong>Data source:</strong> {comp_source_label} &nbsp;\u00b7&nbsp; '
        f'Filter: D{district} &nbsp;\u00b7&nbsp; {tenure} &nbsp;\u00b7&nbsp; {property_type} &nbsp;\u00b7&nbsp; Radius: {proximity_label}<br>'
        f'URA records all lodged caveats for private residential sales in Singapore. '
        f'Comps are filtered by proximity, district, tenure and property type.</div>',
        unsafe_allow_html=True
    )
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("### 🏢 Competitor Supply Pipeline")
    st.caption("Upcoming private residential developments in this district's pipeline. Filtered by selected proximity radius.")
    
    if filtered_supply:
        supply_data = []
        for p in filtered_supply:
            dist_val = p.get("distance_km")
            dist_str = f"{dist_val:.2f} km" if dist_val is not None else "N/A (Whole District)"
            supply_data.append({
                "Project Name": p.get("project_name", "Unknown"),
                "Estimated Units": p.get("estimated_units", 0),
                "Completion Year": p.get("completion_year", "Unknown"),
                "Distance from Site": dist_str
            })
        df_supply = pd.DataFrame(supply_data)
        # Format units cleanly
        if "Estimated Units" in df_supply.columns:
            df_supply["Estimated Units"] = df_supply["Estimated Units"].apply(lambda x: f"{x:,}" if isinstance(x, int) else x)
        st.dataframe(df_supply, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ No upcoming competitor projects identified in this catchment area pipeline.")

# ── Tab 2: Analytics ─────────────────────────────────────────────────────
with tab2:
    PLOT_BG  = "#0F172A"
    GRID_COL = "#1E293B"
    FONT_COL = "#94A3B8"
    ACCENT1  = "#3B82F6"   # blue
    ACCENT2  = "#F59E0B"   # amber
    BAR_COL  = "#334155"   # slate

    df_raw = pd.DataFrame(filtered_transactions)

    # 1. Summary Metrics Cards
    if not df_raw.empty and "psf" in df_raw.columns:
        proj_counts = df_raw["project"].value_counts()
        most_active_name = proj_counts.index[0] if not proj_counts.empty else "N/A"
        most_active_vol = proj_counts.values[0] if not proj_counts.empty else 0

        max_psf_idx = df_raw["psf"].idxmax()
        max_psf_row = df_raw.loc[max_psf_idx]
        max_psf_val = max_psf_row["psf"]
        max_psf_proj = max_psf_row["project"]

        min_psf_idx = df_raw["psf"].idxmin()
        min_psf_row = df_raw.loc[min_psf_idx]
        min_psf_val = min_psf_row["psf"]
        min_psf_proj = min_psf_row["project"]

        st.markdown('<p class="section-header">catchment market summary</p>', unsafe_allow_html=True)
        c_sum1, c_sum2, c_sum3 = st.columns(3)
        c_sum1.metric("Most Active Project", f"{most_active_name}", f"{most_active_vol} transactions", delta_color="off")
        c_sum2.metric("Highest PSF Transaction", f"SGD {max_psf_val:,.0f} PSF", f"{max_psf_proj}", delta_color="normal")
        c_sum3.metric("Lowest PSF Transaction", f"SGD {min_psf_val:,.0f} PSF", f"{min_psf_proj}", delta_color="inverse")
        st.write("")

    chart_col1, chart_col2 = st.columns(2)

    # Left Column: Pricing Frontier & Distribution
    with chart_col1:
        st.markdown("**PSF vs. Size Pricing Frontier**")
        st.caption("Scatter plot mapping Price PSF against Unit Size (sqft). Reveals the pricing frontier and size elasticity (smaller units command higher PSF).")
        if not df_raw.empty and "psf" in df_raw.columns and "size_sqft" in df_raw.columns:
            fig_scatter = px.scatter(
                df_raw,
                x="size_sqft",
                y="psf",
                color="project",
                hover_name="project",
                hover_data={
                    "size_sqft": ":,f",
                    "price_sgd": ":$,.0f",
                    "psf": ":$,.0f",
                    "floor": True,
                    "type_of_sale": True
                },
                labels={"size_sqft": "Unit Size (sqft)", "psf": "Price (SGD PSF)", "project": "Project"},
                template="plotly_dark"
            )

            fig_scatter.update_layout(
                height=320,
                plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
                font=dict(color=FONT_COL, size=10),
                margin=dict(t=10, b=20, l=10, r=10),
                xaxis=dict(gridcolor=GRID_COL),
                yaxis=dict(gridcolor=GRID_COL),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown("**Catchment Capital Value Distribution (PSF)**")
        st.caption("Distribution of transacted capital values (PSF) in this catchment. The dashed line marks the strict Median PSF benchmark.")
        if not df_raw.empty and "psf" in df_raw.columns:
            fig_hist = px.histogram(
                df_raw.dropna(subset=["psf"]),
                x="psf",
                nbins=20,
                color_discrete_sequence=[ACCENT1],
                labels={"psf": "PSF (SGD)", "count": "# Transactions"},
                template="plotly_dark",
            )
            # Strict Median PSF Line (matches GoldenRecord metrics)
            fig_hist.add_vline(
                x=stats.get("median_psf", 0),
                line_dash="dash",
                line_color=ACCENT2,
                annotation_text=f"Median: SGD {stats.get('median_psf',0):,.0f} PSF",
                annotation_font_color=ACCENT2,
                annotation_position="top right",
            )

            fig_hist.update_layout(
                height=280,
                showlegend=False,
                plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
                font=dict(color=FONT_COL, size=10),
                margin=dict(t=20, b=20, l=10, r=10),
                xaxis=dict(gridcolor=GRID_COL, tickfont=dict(size=9)),
                yaxis=dict(gridcolor=GRID_COL),
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    # Right Column: Age Premium & Trends
    with chart_col2:
        st.markdown("**Price vs. Building Age Correlation**")
        st.caption("Scatter plot mapping Unit Price PSF against Building Age (Years). Illustrates the negative correlation of pricing with leasehold depreciation (older projects sit lower).")
        if not df_raw.empty and "psf" in df_raw.columns:
            # Calculate age for each transaction
            from analytics import get_numeric_age
            
            ages = []
            for _, tx in df_raw.iterrows():
                proj_name = tx.get("project", "")
                age = get_numeric_age(proj_name, tx.get("type_of_sale", ""))
                ages.append(age)
                
            df_raw["age"] = ages
            
            fig_age = px.scatter(
                df_raw,
                x="age",
                y="psf",
                color="project",
                hover_name="project",
                hover_data={
                    "age": True,
                    "size_sqft": ":,f",
                    "price_sgd": ":$,.0f",
                    "psf": ":$,.0f",
                    "floor": True
                },
                labels={"age": "Building Age (Years)", "psf": "Price (SGD PSF)", "project": "Project"},
                template="plotly_dark"
            )
            fig_age.update_layout(
                height=320,
                plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
                font=dict(color=FONT_COL, size=10),
                margin=dict(t=10, b=20, l=10, r=10),
                xaxis=dict(gridcolor=GRID_COL, dtick=5),
                yaxis=dict(gridcolor=GRID_COL),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_age, use_container_width=True)

        st.markdown("**Quarterly Transaction Volume & Price Trend**")
        st.caption("Catchment transaction velocity (bar, left axis) mapped against Average PSF trend (line, right axis) over time.")
        quarterly_list = stats.get("quarterly", [])
        if quarterly_list:
            df_q = pd.DataFrame(quarterly_list)
            fig_q = go.Figure()
            
            fig_q.add_trace(
                go.Bar(
                    x=df_q["quarter"],
                    y=df_q["volume"],
                    name="Volume",
                    marker_color=BAR_COL,
                    yaxis="y1"
                )
            )
            
            fig_q.add_trace(
                go.Scatter(
                    x=df_q["quarter"],
                    y=df_q["avg_psf"],
                    name="Avg PSF",
                    line=dict(color=ACCENT2, width=3),
                    marker=dict(size=8),
                    yaxis="y2"
                )
            )
            
            fig_q.update_layout(
                height=280,
                template="plotly_dark",
                plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
                font=dict(color=FONT_COL, size=10),
                margin=dict(t=20, b=20, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(gridcolor=GRID_COL),
                yaxis=dict(
                    title="Volume (# Txns)",
                    gridcolor=GRID_COL,
                    side="left"
                ),
                yaxis2=dict(
                    title="Avg PSF (SGD)",
                    side="right",
                    overlaying="y",
                    showgrid=False
                )
            )
            st.plotly_chart(fig_q, use_container_width=True)

# ── Tab 3: AI Assessment ─────────────────────────────────────────────────
with tab3:
    st.markdown('<p class="section-header">Golden Record Data Provenance</p>', unsafe_allow_html=True)
    st.caption("The table below documents the single source of truth (Golden Record) compiled from raw structured and unstructured data, tracing the exact source and extraction method.")
    
    # Extract values from golden_record
    c_gpr = golden_record.legal_constraints.gross_plot_ratio
    c_height = golden_record.legal_constraints.max_allowable_height
    c_conds = ", ".join(golden_record.legal_constraints.special_conditions) if golden_record.legal_constraints.special_conditions else "None"
    
    s_units = golden_record.supply_threats.nearby_uncompleted_units
    s_window = golden_record.supply_threats.expected_completion_window
    
    v_psf = golden_record.valuation_comparables.median_historical_psf
    v_count = golden_record.valuation_comparables.transaction_count_analyzed
    
    m_avg = golden_record.market_analytics.average_psf if golden_record.market_analytics else None
    m_min = golden_record.market_analytics.min_psf if golden_record.market_analytics else None
    m_max = golden_record.market_analytics.max_psf if golden_record.market_analytics else None
    m_new = golden_record.market_analytics.new_sale_percent if golden_record.market_analytics else None
    m_age = golden_record.market_analytics.average_age if golden_record.market_analytics else None
    m_active = golden_record.market_analytics.most_active_project if golden_record.market_analytics else None

    # Format values
    gpr_val = f"{c_gpr:.1f}x" if c_gpr is not None else "Data Insufficient"
    height_val = f"{c_height} storeys" if c_height is not None else "Data Insufficient"
    units_val = f"{s_units:,} units" if s_units is not None else "Data Insufficient"
    psf_val = f"SGD {v_psf:,.0f} PSF" if v_psf is not None else "Data Insufficient"
    count_val = f"{v_count:,} transactions" if v_count is not None else "Data Insufficient"
    
    avg_psf_val = f"SGD {m_avg:,.0f} PSF" if m_avg is not None else "Data Insufficient"
    range_psf_val = f"SGD {m_min:,.0f} – {m_max:,.0f} PSF" if (m_min is not None and m_max is not None) else "Data Insufficient"
    new_pct_val = f"{m_new:.1f}%" if m_new is not None else "Data Insufficient"
    age_val = f"{m_age:.1f} years" if m_age is not None else "Data Insufficient"
    active_val = m_active if m_active else "Data Insufficient"

    # Create the markdown provenance table
    provenance_data = [
        {"Parameter / Metric": "Gross Plot Ratio", "Value": gpr_val, "Source": "URA Master Plan / Excerpts", "Method": "LLM Structured Parsing / Catalogue Fallback"},
        {"Parameter / Metric": "Max Allowable Height", "Value": height_val, "Source": "URA Master Plan / Excerpts", "Method": "LLM Structured Parsing / Catalogue Fallback"},
        {"Parameter / Metric": "Special Conditions", "Value": c_conds, "Source": "URA Tender Excerpts", "Method": "LLM Extraction Agent"},
        {"Parameter / Metric": "Nearby Uncompleted Units", "Value": units_val, "Source": "URA Pipeline database", "Method": f"Spatial Proximity filter ({proximity_label})"},
        {"Parameter / Metric": "Expected Completion Window", "Value": s_window, "Source": "URA Pipeline database", "Method": f"Spatial Proximity filter ({proximity_label})"},
        {"Parameter / Metric": "Median Historical PSF", "Value": psf_val, "Source": "URA Transactions API / CSV", "Method": f"Spatial Proximity filter ({proximity_label}) & Median calc"},
        {"Parameter / Metric": "Transaction Count Analyzed", "Value": count_val, "Source": "URA Transactions API / CSV", "Method": f"Spatial Proximity filter ({proximity_label})"},
        {"Parameter / Metric": "Average Historical PSF", "Value": avg_psf_val, "Source": "URA Transactions API / CSV", "Method": f"Spatial Proximity filter ({proximity_label}) & Mean calc"},
        {"Parameter / Metric": "Historical PSF Range", "Value": range_psf_val, "Source": "URA Transactions API / CSV", "Method": f"Spatial Proximity filter ({proximity_label}) & Min/Max calc"},
        {"Parameter / Metric": "New Sale Percentage", "Value": new_pct_val, "Source": "URA Transactions API / CSV", "Method": f"Spatial Proximity filter ({proximity_label}) & Split calc"},
        {"Parameter / Metric": "Average Project Age", "Value": age_val, "Source": "URA Transactions API / CSV & Database", "Method": f"Spatial Proximity filter ({proximity_label}) & Age calc"},
        {"Parameter / Metric": "Most Active Comparable", "Value": active_val, "Source": "URA Transactions API / CSV", "Method": f"Spatial Proximity filter ({proximity_label}) & Mode calc"}
    ]
    
    df_provenance = pd.DataFrame(provenance_data)
    st.dataframe(df_provenance, use_container_width=True, hide_index=True)

    # Sidebar / Inspector option for Golden Record JSON
    with st.expander("🔍 Inspect Compiled Golden Record JSON Payload"):
        st.info(
            "💡 **Dynamic Ingestion In Action**: This JSON represents the compiled Golden Record. It is NOT hardcoded. "
            "The pricing metrics (median/mean/range) and competitor supply stats (units/windows) are computed dynamically "
            "by executing geospatial calculations over the filtered datasets. The legal constraints are extracted on the "
            "fly from the PDF tender excerpts using your selected LLM provider."
        )
        col_json_rec, col_json_flat = st.columns(2)
        with col_json_rec:
            st.markdown("**Golden Record JSON**")
            st.json(golden_record.model_dump_json(indent=2))
        with col_json_flat:
            st.markdown("**Source Context Parameters**")
            st.write(site_details)

    st.divider()

    st.markdown('<p class="section-header">AI Synthesis & Draft Memo Generation</p>', unsafe_allow_html=True)
    
    # Synthesis Trigger Button
    if "ai_assessment" not in st.session_state:
        st.session_state["ai_assessment"] = None

    if st.session_state["ai_assessment"] is None:
        # Prompt user to generate
        st.info("ℹ️ The assessment memo will not generate automatically to avoid unnecessary API cost/churn. Review the provenance table above and click below to trigger.")
        if st.button("🤖 Run AI Synthesis & Assessment", type="primary", use_container_width=True):
            with st.spinner("Executing Zero-Hallucination AI Synthesis on Golden Record..."):
                assessment = generate_assessment(
                    golden_record,
                    llm_provider=llm_provider,
                    ollama_url=ollama_url,
                    ollama_model=ollama_model
                )
                st.session_state["ai_assessment"] = assessment
                st.session_state["edited_memo"] = assessment
                st.rerun()
    else:
        # We have an assessment. Show the button to rerun and the editor.
        col_btn_rerun, col_btn_clear = st.columns([3, 1])
        with col_btn_rerun:
            if st.button("🔄 Regenerate AI Synthesis", type="secondary", use_container_width=True):
                with st.spinner("Re-executing AI Synthesis on Golden Record..."):
                    assessment = generate_assessment(
                        golden_record,
                        llm_provider=llm_provider,
                        ollama_url=ollama_url,
                        ollama_model=ollama_model
                    )
                    st.session_state["ai_assessment"] = assessment
                    st.session_state["edited_memo"] = assessment
                    st.rerun()
        with col_btn_clear:
            if st.button("🗑️ Clear", type="secondary", use_container_width=True):
                del st.session_state["ai_assessment"]
                if "edited_memo" in st.session_state:
                    del st.session_state["edited_memo"]
                st.rerun()

        st.markdown("### 📝 Draft Assessment Memo Editor")
        st.caption("Make any edits directly below. Your edits will be saved and exported when clicking the button below.")
        
        # Editable Text Area for the Human Analyst
        edited_memo_content = st.text_area(
            label="Draft Assessment Memo Editor",
            value=st.session_state.get("edited_memo", ""),
            height=650,
            key="edited_memo",
            help="Edit the draft memo text as needed. Your overrides will be preserved when downloading.",
            label_visibility="collapsed"
        )

        st.write("") # spacing
        
        # Export Button
        st.download_button(
            label="📥 Export Finalized Memo (.md)",
            data=st.session_state.get("edited_memo", ""),
            file_name=f"{site_details['site_name'].replace(' ', '_')}_Viability_Memo.md",
            mime="text/markdown",
            use_container_width=True
        )

    # ── AI Insights Overlay ──
    st.divider()
    st.markdown('<p class="section-header">🤖 Automated Market & Pricing Insights</p>', unsafe_allow_html=True)
    with st.container(border=True):
        from ai_analyst import generate_chart_insights
        insights = generate_chart_insights(
            stats,
            target_launch_psf,
            breakeven_psf,
            llm_provider=llm_provider,
            ollama_url=ollama_url,
            ollama_model=ollama_model
        )
        st.markdown(insights)
