import os
import json
import math
import time
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Path to the locally cached URA Sale Sites GeoJSON file and geocoding cache
_dir = os.path.dirname(os.path.abspath(__file__))
GEOJSON_PATH = os.path.join(_dir, "ura_sale_sites.geojson")
CACHE_PATH = os.path.join(_dir, "onemap_geocoding_cache.json")

# Pre-computed coordinates for the 15 URA GLS catalogue sites
# Sourced from official geocoding via SLA OneMap API
GLS_SITES_COORDS = {
    "Jurong Lake District (Master Developer Site)": {"lat": 1.33035, "lon": 103.74354},
    "Lentor Gardens": {"lat": 1.38264, "lon": 103.83305},
    "Lentor Central (Parcel B)": {"lat": 1.38559, "lon": 103.83401},
    "Tampines Ave 11 (EC)": {"lat": 1.36610, "lon": 103.93347},
    "Clementi Avenue 1": {"lat": 1.31008, "lon": 103.76836},
    "Jalan Tembusu": {"lat": 1.30090, "lon": 103.89670},
    "Buona Vista Road": {"lat": 1.30443, "lon": 103.78854},
    "Media Circle (Parcel A)": {"lat": 1.30130, "lon": 103.78870},
    "Hillview Rise": {"lat": 1.36358, "lon": 103.76318},
    "Dunman Road": {"lat": 1.31300, "lon": 103.89300},
    "Pine Grove (Parcel A)": {"lat": 1.31936, "lon": 103.77404},
    "Tengah Garden Avenue (EC)": {"lat": 1.35561, "lon": 103.73103},
    "Marina Gardens Lane": {"lat": 1.27623, "lon": 103.86313},
    "Upper Thomson Road (Parcel B)": {"lat": 1.37008, "lon": 103.82768},
    "Senja Close (EC)": {"lat": 1.38840, "lon": 103.76184},
}

# ── In-Memory Cache Loading at Module Startup ───────────────────────────────
_geojson_cache_in_memory = None
if os.path.exists(GEOJSON_PATH):
    try:
        with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
            _geojson_cache_in_memory = json.load(f)
    except Exception as e:
        print(f"Error loading URA Sale Sites GeoJSON: {e}")

_onemap_cache_in_memory = {}
if os.path.exists(CACHE_PATH):
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            raw_cache = json.load(f)
            _onemap_cache_in_memory = {k.strip().upper(): v for k, v in raw_cache.items()}
    except Exception:
        pass


@st.cache_resource
def load_geojson_cache() -> dict:
    """Return the cached URA Sale Sites GeoJSON collection from memory."""
    return _geojson_cache_in_memory


@st.cache_data
def geocode_onemap(address: str) -> tuple[float, float]:
    """
    Query coordinates for an address from SLA OneMap geocoding API.
    Uses a persistent local file cache in memory to prevent repeated API calls.
    Returns (latitude, longitude) or (None, None).
    """
    if not address or not address.strip():
        return None, None
        
    address_clean = address.strip().upper()
    if "," in address_clean:
        address_clean = address_clean.split(",")[0].strip().upper()
        
    # 1. Check in-memory cache
    if address_clean in _onemap_cache_in_memory:
        coords = _onemap_cache_in_memory[address_clean]
        return coords.get("lat"), coords.get("lon")
        
    # 2. Query SLA OneMap Search API
    url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={address_clean}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
    try:
        time.sleep(0.1)  # Rate limit prevention
        resp = requests.get(url, timeout=10)
        if resp.status_code == 429:
            time.sleep(1.5)  # Rate limit cooling off
            resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        
        if results:
            first = results[0]
            lat = float(first.get("LATITUDE"))
            lon = float(first.get("LONGITUDE"))
            
            # Save to cache
            _onemap_cache_in_memory[address_clean] = {"lat": lat, "lon": lon}
            try:
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(_onemap_cache_in_memory, f, indent=2)
            except Exception as e:
                print(f"Error saving OneMap cache: {e}")
            return lat, lon
            
        # 3. Fallback search by splitting intersections (e.g. "Road A / Road B" -> search "Road A")
        if "/" in address_clean:
            part = address_clean.split("/")[0].strip().upper()
            url2 = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={part}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
            resp2 = requests.get(url2, timeout=10)
            results2 = resp2.json().get("results", [])
            if results2:
                first = results2[0]
                lat = float(first.get("LATITUDE"))
                lon = float(first.get("LONGITUDE"))
                
                _onemap_cache_in_memory[address_clean] = {"lat": lat, "lon": lon}
                try:
                    with open(CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(_onemap_cache_in_memory, f, indent=2)
                except Exception as e:
                    print(f"Error saving OneMap cache: {e}")
                return lat, lon
    except Exception as e:
        print(f"OneMap geocoding error for '{address_clean}': {e}")
        
    return None, None

def find_site_in_geojson(site_name: str, address: str, geojson_data: dict) -> dict:
    """
    Scan local GeoJSON features to find a polygon matching the site name or address.
    Prioritizes exact string matching before running keyword fallback checks.
    """
    if not geojson_data or "features" not in geojson_data:
        return None
        
    features = geojson_data["features"]
    
    # Pass 1: Exact matches (case-insensitive check of full name/address)
    for feature in features:
        props = feature.get("properties", {})
        location_field = str(props.get("LOCATION", "")).lower()
        name_field = str(props.get("name", "")).lower()
        
        # Check if full name is in LOCATION/name or vice versa
        if site_name:
            s_name_lower = site_name.lower()
            if s_name_lower in location_field or location_field in s_name_lower or s_name_lower in name_field or name_field in s_name_lower:
                return feature
        if address:
            s_addr_lower = address.lower()
            if s_addr_lower in location_field or location_field in s_addr_lower:
                return feature
                
    # Pass 2: Cleaned keyword fallback
    keywords = []
    for kw in [site_name, address]:
        if kw:
            clean = kw.replace("(EC)", "").replace("(Parcel A)", "").replace("(Parcel B)", "").strip()
            if len(clean) > 3:
                keywords.append(clean)
                
    if not keywords:
        return None
        
    for feature in features:
        props = feature.get("properties", {})
        location_field = str(props.get("LOCATION", "")).lower()
        name_field = str(props.get("name", "")).lower()
        devt_allow = str(props.get("DEVT_ALLOW", "")).lower()
        
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in location_field or kw_lower in name_field or kw_lower in devt_allow:
                return feature
                
    return None

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two lat/lon points using Haversine formula."""
    if None in (lat1, lon1, lat2, lon2):
        return 99999.0
    R = 6371.0  # Radius of Earth in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def generate_selection_map(
    gls_sites: list[dict],
    selected_site_name: str = None,
    comparables: list[dict] = None,
    competitors: list[dict] = None,
    radius_km: float = None
):
    """
    Generates a full-width interactive Folium Leaflet map of all available GLS sites.
    Mutes inactive sites with Blue pins and highlights the active selected site with an Orange pin.
    Plots neighboring comparable properties and pipeline competitors, and draws a district catchment circle.
    Natively streams SLA OneMap basemap tiles.
    """
    import folium
    
    # 1. Resolve selected site coordinates or default to Singapore center
    selected_lat, selected_lon = 1.3521, 103.8198
    zoom = 11
    
    for site in gls_sites:
        name = site["name"]
        if name == selected_site_name:
            if "Custom Site" in name:
                if site.get("address"):
                    lat, lon = geocode_onemap(site["address"])
                    if lat and lon:
                        selected_lat, selected_lon = lat, lon
                        zoom = 13
            else:
                coords = GLS_SITES_COORDS.get(name)
                if coords:
                    selected_lat, selected_lon = coords["lat"], coords["lon"]
                    zoom = 13
            break
            
    # 2. Create Folium Map on SLA OneMap
    m = folium.Map(
        location=[selected_lat, selected_lon],
        zoom_start=zoom,
        tiles="https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png",
        attr="SLA OneMap",
        zoom_control=True
    )
    
    # 3. Add proximity catchment circle if selected, or dynamic district bounds if 'Whole District' is selected
    if selected_site_name:
        if radius_km is not None:
            folium.Circle(
                location=[selected_lat, selected_lon],
                radius=radius_km * 1000,
                color="#D97706", # amber-600
                fill=True,
                fill_color="#F59E0B", # amber-500
                fill_opacity=0.07,
                dash_array="6, 9",
                weight=1.5
            ).add_to(m)
        elif comparables:
            # Find maximum distance of geocoded comparables in the district to draw a bounding catchment circle
            comp_dists = [
                haversine_distance(selected_lat, selected_lon, tx.get("lat"), tx.get("lon"))
                for tx in comparables
                if tx.get("lat") and tx.get("lon")
            ]
            if comp_dists:
                max_dist = max(comp_dists)
                # Cap the maximum visual circle at 15km to avoid rendering issues
                max_dist = min(max_dist, 15.0)
                folium.Circle(
                    location=[selected_lat, selected_lon],
                    radius=max_dist * 1.1 * 1000, # 10% padding
                    color="#475569", # slate-600
                    fill=True,
                    fill_color="#64748B", # slate-500
                    fill_opacity=0.03,
                    dash_array="8, 12",
                    weight=1.5
                ).add_to(m)
        
    # 4. Add GLS Site Markers with HTML Popups
    for site in gls_sites:
        name = site["name"]
        
        # Resolve coordinates
        if "Custom Site" in name:
            if name == selected_site_name and site.get("address"):
                lat, lon = geocode_onemap(site["address"])
            else:
                continue
        else:
            coords = GLS_SITES_COORDS.get(name)
            if coords:
                lat, lon = coords["lat"], coords["lon"]
            else:
                continue
                
        if not lat or not lon:
            continue
            
        is_selected = (name == selected_site_name)
        color = "orange" if is_selected else "blue"
        
        # Format HTML popup card
        popup_html = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 12px; width: 230px; line-height: 1.4; color: #1E293B;">
            <h4 style="margin: 0 0 6px 0; color: #1E3A8A; font-size: 13px; border-bottom: 1px solid #E2E8F0; padding-bottom: 4px;">{name}</h4>
            <table style="width: 100%; border-collapse: collapse; margin-top: 4px;">
                <tr><td style="color:#64748B; font-weight: 500; padding: 2px 0;">District:</td><td style="font-weight:bold; padding: 2px 0; text-align: right;">D{site['district']}</td></tr>
                <tr><td style="color:#64748B; font-weight: 500; padding: 2px 0;">Site Area:</td><td style="font-weight:bold; padding: 2px 0; text-align: right;">{site['site_area_sqm']:,} sqm</td></tr>
                <tr><td style="color:#64748B; font-weight: 500; padding: 2px 0;">Plot Ratio:</td><td style="font-weight:bold; padding: 2px 0; text-align: right;">{site['plot_ratio']:.1f}x</td></tr>
                <tr><td style="color:#64748B; font-weight: 500; padding: 2px 0;">Tenure:</td><td style="font-weight:bold; padding: 2px 0; text-align: right;">{site['tenure']}</td></tr>
            </table>
        </div>
        """
        
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=name,
            icon=folium.Icon(color=color, icon="info-sign")
        ).add_to(m)
        
    # 5. Add Comparable transactions (Comps) circle markers
    if comparables:
        unique_comps = {}
        for tx in comparables:
            proj = tx.get("project")
            p_lat, p_lon = tx.get("lat"), tx.get("lon")
            if proj and p_lat and p_lon and proj not in unique_comps:
                proj_txs = [t for t in comparables if t.get("project") == proj]
                avg_psf = sum(t.get("psf", 0) for t in proj_txs) / len(proj_txs) if proj_txs else 0
                unique_comps[proj] = {
                    "lat": p_lat,
                    "lon": p_lon,
                    "avg_psf": avg_psf,
                    "count": len(proj_txs)
                }
                
        for proj, data in unique_comps.items():
            tooltip_html = f"""
            <div style="font-family: sans-serif; font-size: 11px; width: 190px; line-height: 1.3; color: #1E293B; padding: 2px;">
                <h5 style="margin: 0 0 4px 0; color: #1D4ED8; font-size: 12px; font-weight: bold;">🏠 {proj}</h5>
                <b>Status:</b> Comparable private resi comp<br>
                <b>Distance:</b> {haversine_distance(selected_lat, selected_lon, data['lat'], data['lon']):.2f} km<br>
                <b>Volume:</b> {data['count']} transactions<br>
                <b>Avg PSF:</b> SGD {data['avg_psf']:,.0f} PSF
            </div>
            """
            folium.CircleMarker(
                location=[data["lat"], data["lon"]],
                radius=6,
                tooltip=folium.Tooltip(tooltip_html, sticky=True),
                color="#1D4ED8", # blue-700
                fill=True,
                fill_color="#3B82F6", # blue-500
                fill_opacity=0.75,
                weight=1
            ).add_to(m)

    # 6. Add Competitor pipeline project markers
    if competitors:
        for p in competitors:
            p_lat, p_lon = p.get("lat"), p.get("lon")
            if p_lat and p_lon:
                proj_name = p.get("project_name", "Unknown")
                units = p.get("estimated_units", 0)
                year = p.get("completion_year", "Unknown")
                tooltip_html = f"""
                <div style="font-family: sans-serif; font-size: 11px; width: 190px; line-height: 1.3; color: #1E293B; padding: 2px;">
                    <h5 style="margin: 0 0 4px 0; color: #6D28D9; font-size: 12px; font-weight: bold;">🏢 {proj_name}</h5>
                    <b>Status:</b> Upcoming supply pipeline<br>
                    <b>Distance:</b> {haversine_distance(selected_lat, selected_lon, p_lat, p_lon):.2f} km<br>
                    <b>Est. Units:</b> {units:,} units<br>
                    <b>Est. Completion:</b> {year}
                </div>
                """
                folium.CircleMarker(
                    location=[p_lat, p_lon],
                    radius=6.5,
                    tooltip=folium.Tooltip(tooltip_html, sticky=True),
                    color="#6D28D9", # purple-700
                    fill=True,
                    fill_color="#8B5CF6", # purple-500
                    fill_opacity=0.75,
                    weight=1
                ).add_to(m)

    return m

def filter_transactions_by_proximity(
    transactions: list[dict],
    gls_lat: float,
    gls_lon: float,
    radius_km: float
) -> list[dict]:
    """
    Filters comps by spatial proximity. Geocodes unique project names and
    calculates haversine distance from the selected GLS plot.
    """
    if not transactions or gls_lat is None or gls_lon is None:
        return transactions
        
    # 1. Identify unique project names to geocode
    unique_projects = list(set(tx.get("project", "") for tx in transactions if tx.get("project")))
    
    # 2. Bulk geocode unique projects and store in project coordinates mapping
    project_coords = {}
    for proj in unique_projects:
        lat, lon = geocode_onemap(proj)
        if lat and lon:
            project_coords[proj] = (lat, lon)
            
    # 3. Filter transactions based on computed haversine distance
    filtered_txns = []
    for tx in transactions:
        proj = tx.get("project")
        if proj in project_coords:
            p_lat, p_lon = project_coords[proj]
            dist = haversine_distance(gls_lat, gls_lon, p_lat, p_lon)
            tx["distance_km"] = round(dist, 2)
            tx["lat"] = p_lat
            tx["lon"] = p_lon
            if radius_km is None or dist <= radius_km:
                filtered_txns.append(tx)
        else:
            if radius_km is None:
                tx["distance_km"] = None
                tx["lat"] = None
                tx["lon"] = None
                filtered_txns.append(tx)
                
    return filtered_txns

def filter_pipeline_by_proximity(
    db_projects: list[dict],
    gls_lat: float,
    gls_lon: float,
    radius_km: float
) -> list[dict]:
    """
    Filters upcoming competitor pipeline projects in the planning district by proximity.
    """
    if not db_projects or gls_lat is None or gls_lon is None:
        return db_projects
        
    filtered_projects = []
    for p in db_projects:
        name = p.get("project_name", "")
        lat, lon = geocode_onemap(name)
        if lat and lon:
            dist = haversine_distance(gls_lat, gls_lon, lat, lon)
            p["distance_km"] = round(dist, 2)
            p["lat"] = lat
            p["lon"] = lon
            if radius_km is None or dist <= radius_km:
                filtered_projects.append(p)
        else:
            if radius_km is None:
                p["distance_km"] = None
                p["lat"] = None
                p["lon"] = None
                filtered_projects.append(p)
                
    return filtered_projects
