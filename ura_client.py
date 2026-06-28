"""
ura_client.py
-------------
Fetches private residential transaction data from URA / data.gov.sg.
Falls back to a realistic mock dataset if no API key is configured.
"""

import os
import random
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

URA_ACCESS_KEY = os.getenv("URA_ACCESS_KEY")

# ── District Map ─────────────────────────────────────────────────────────────

DISTRICT_MAP = {
    "1":  "Marina / Raffles Place / Cecil",
    "2":  "Tanjong Pagar / Chinatown",
    "4":  "Harbourfront / Sentosa / Telok Blangah",
    "5":  "Buona Vista / West Coast / Clementi",
    "9":  "Orchard / River Valley",
    "10": "Holland / Tanglin / Bukit Timah",
    "11": "Newton / Novena",
    "14": "Eunos / Geylang / Kembangan",
    "15": "Katong / Joo Chiat / East Coast",
    "16": "Bedok / Upper East Coast",
    "18": "Tampines / Pasir Ris",
    "19": "Hougang / Punggol / Sengkang",
    "20": "Bishan / Ang Mo Kio / Thomson",
    "21": "Clementi Park / Upper Bukit Timah",
    "22": "Boon Lay / Jurong / Jurong East",
    "23": "Hillview / Bukit Panjang / Choa Chu Kang",
    "25": "Kranji / Woodlands",
    "27": "Yishun / Sembawang",
    "28": "Seletar / Punggol North",
}

# ── Project Database — Single Source of Truth ────────────────────────────────
# Each entry defines a project's district, completion year (None = BUC),
# age-based PSF multiplier (1.0 = full market rate, <1.0 = older/cheaper),
# and any freehold flag.
# When completion_year is None, the project is treated as BUC (generates New Sale).

PROJECT_DATABASE: list[dict] = [
    # ── District 1 — Marina / Raffles Place ──────────────────────────────────
    {"name": "Marina One Residences",       "district": "1",  "completion_year": 2017, "age_mult": 0.90, "freehold": True},
    {"name": "The Clift",                   "district": "1",  "completion_year": 2012, "age_mult": 0.85, "freehold": True},
    {"name": "Spottiswoode 18",             "district": "1",  "completion_year": 2008, "age_mult": 0.80, "freehold": True},
    {"name": "Icon",                        "district": "1",  "completion_year": 2007, "age_mult": 0.80, "freehold": True},
    {"name": "Marina Gardens Residences",   "district": "1",  "completion_year": None, "age_mult": 1.00, "freehold": False},
    # ── District 2 — Tanjong Pagar ───────────────────────────────────────────
    {"name": "Altez",                       "district": "2",  "completion_year": 2014, "age_mult": 0.85, "freehold": True},
    {"name": "Skysuites@Anson",             "district": "2",  "completion_year": 2013, "age_mult": 0.83, "freehold": False},
    {"name": "1 Shenton",                   "district": "2",  "completion_year": 2011, "age_mult": 0.80, "freehold": True},
    {"name": "The Pinnacle",               "district": "2",  "completion_year": 2009, "age_mult": 0.78, "freehold": False},
    # ── District 4 — Harbourfront / Sentosa ──────────────────────────────────
    {"name": "Reflections at Keppel Bay",   "district": "4",  "completion_year": 2011, "age_mult": 0.85, "freehold": False},
    {"name": "Caribbean at Keppel Bay",     "district": "4",  "completion_year": 2004, "age_mult": 0.75, "freehold": False},
    {"name": "Corals at Keppel Bay",        "district": "4",  "completion_year": 2016, "age_mult": 0.88, "freehold": False},
    {"name": "Seascape",                    "district": "4",  "completion_year": 2011, "age_mult": 0.86, "freehold": False},
    # ── District 5 — Buona Vista / Clementi ──────────────────────────────────
    {"name": "Whistler Grand",              "district": "5",  "completion_year": 2022, "age_mult": 0.95, "freehold": False},
    {"name": "Twin Vew",                    "district": "5",  "completion_year": 2021, "age_mult": 0.94, "freehold": False},
    {"name": "The Clement Canopy",          "district": "5",  "completion_year": 2020, "age_mult": 0.92, "freehold": False},
    {"name": "Parc Clematis",               "district": "5",  "completion_year": 2023, "age_mult": 0.97, "freehold": False},
    {"name": "The Hill @ One-North",        "district": "5",  "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Blossoms By The Park",        "district": "5",  "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Media Circle Residences",     "district": "5",  "completion_year": None, "age_mult": 1.00, "freehold": False},
    # ── District 9 — Orchard ─────────────────────────────────────────────────
    {"name": "The Orchard Residences",      "district": "9",  "completion_year": 2010, "age_mult": 0.85, "freehold": True},
    {"name": "Cairnhill Nine",              "district": "9",  "completion_year": 2018, "age_mult": 0.92, "freehold": True},
    {"name": "Boulevard 88",               "district": "9",  "completion_year": 2021, "age_mult": 0.96, "freehold": True},
    {"name": "3 Cuscaden",                  "district": "9",  "completion_year": 2022, "age_mult": 0.97, "freehold": True},
    # ── District 10 — Holland / Tanglin ──────────────────────────────────────
    {"name": "Leedon Residence",            "district": "10", "completion_year": 2015, "age_mult": 0.88, "freehold": True},
    {"name": "The Nassim",                  "district": "10", "completion_year": 2018, "age_mult": 0.92, "freehold": True},
    {"name": "Gramercy Park",               "district": "10", "completion_year": 2016, "age_mult": 0.90, "freehold": True},
    {"name": "Cluny Park Residence",        "district": "10", "completion_year": 2014, "age_mult": 0.87, "freehold": True},
    # ── District 11 — Newton / Novena ────────────────────────────────────────
    {"name": "Pullman Residences",          "district": "11", "completion_year": 2022, "age_mult": 0.96, "freehold": True},
    {"name": "The Atelier",                 "district": "11", "completion_year": 2023, "age_mult": 0.97, "freehold": True},
    {"name": "Dunearn 386",                 "district": "11", "completion_year": 2020, "age_mult": 0.93, "freehold": True},
    {"name": "Novena",                      "district": "11", "completion_year": 2010, "age_mult": 0.82, "freehold": True},
    # ── District 14 — Eunos / Geylang ────────────────────────────────────────
    {"name": "Sims Urban Oasis",            "district": "14", "completion_year": 2017, "age_mult": 0.88, "freehold": False},
    {"name": "Kingsford Waterbay",          "district": "14", "completion_year": 2018, "age_mult": 0.89, "freehold": False},
    {"name": "Parc Esta",                   "district": "14", "completion_year": 2021, "age_mult": 0.94, "freehold": False},
    {"name": "Sims Drive",                  "district": "14", "completion_year": 2006, "age_mult": 0.78, "freehold": False},
    # ── District 15 — East Coast ─────────────────────────────────────────────
    {"name": "Amber Park",                  "district": "15", "completion_year": 2023, "age_mult": 0.97, "freehold": True},
    {"name": "NYON",                        "district": "15", "completion_year": 2022, "age_mult": 0.96, "freehold": True},
    {"name": "One Meyer",                   "district": "15", "completion_year": 2023, "age_mult": 0.97, "freehold": True},
    {"name": "Meyer Mansion",               "district": "15", "completion_year": 2024, "age_mult": 0.99, "freehold": True},
    {"name": "Grand Dunman",                "district": "15", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Tembusu Grand",               "district": "15", "completion_year": None, "age_mult": 1.00, "freehold": False},
    # ── District 16 — Bedok ──────────────────────────────────────────────────
    {"name": "Eastwood Regency",            "district": "16", "completion_year": 2014, "age_mult": 0.85, "freehold": True},
    {"name": "The Glades",                  "district": "16", "completion_year": 2016, "age_mult": 0.87, "freehold": False},
    {"name": "The Jovell",                  "district": "16", "completion_year": 2022, "age_mult": 0.95, "freehold": False},
    {"name": "Kew Lodge",                   "district": "16", "completion_year": 2006, "age_mult": 0.78, "freehold": True},
    # ── District 18 — Tampines ───────────────────────────────────────────────
    {"name": "Parc Central Residences",     "district": "18", "completion_year": 2022, "age_mult": 0.94, "freehold": False},
    {"name": "Treasure at Tampines",        "district": "18", "completion_year": 2023, "age_mult": 0.96, "freehold": False},
    {"name": "The Tapestry",                "district": "18", "completion_year": 2021, "age_mult": 0.93, "freehold": False},
    {"name": "Ola",                         "district": "18", "completion_year": 2022, "age_mult": 0.94, "freehold": False},
    {"name": "Tampines Ave 11 Mixed Use",   "district": "18", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Tenet (EC)",                  "district": "18", "completion_year": None, "age_mult": 1.00, "freehold": False},
    # ── District 19 — Hougang / Punggol ──────────────────────────────────────
    {"name": "Piermont Grand",              "district": "19", "completion_year": 2022, "age_mult": 0.94, "freehold": False},
    {"name": "Rivercove Residences",        "district": "19", "completion_year": 2019, "age_mult": 0.90, "freehold": False},
    {"name": "Parc Komo",                   "district": "19", "completion_year": 2023, "age_mult": 0.96, "freehold": True},
    {"name": "The Gazania",                 "district": "19", "completion_year": 2022, "age_mult": 0.94, "freehold": False},
    # ── District 20 — Bishan / Ang Mo Kio / Thomson ──────────────────────────
    {"name": "Sky Vue",                     "district": "20", "completion_year": 2016, "age_mult": 0.88, "freehold": False},
    {"name": "Sky Habitat",                 "district": "20", "completion_year": 2016, "age_mult": 0.88, "freehold": False},
    {"name": "Bishan 8",                    "district": "20", "completion_year": 2005, "age_mult": 0.78, "freehold": False},
    {"name": "Thomson Three",               "district": "20", "completion_year": 2016, "age_mult": 0.88, "freehold": False},
    {"name": "Lentor Hills Residences",     "district": "20", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Lentor Mansion",              "district": "20", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Lentoria",                    "district": "20", "completion_year": None, "age_mult": 1.00, "freehold": False},
    # ── District 21 — Clementi Park / Upper Bukit Timah ──────────────────────
    {"name": "The Trilinq",                 "district": "21", "completion_year": 2017, "age_mult": 0.88, "freehold": False},
    {"name": "Parc Riviera",                "district": "21", "completion_year": 2018, "age_mult": 0.89, "freehold": False},
    {"name": "Lake Grande",                 "district": "21", "completion_year": 2020, "age_mult": 0.92, "freehold": False},
    {"name": "The Criterion",               "district": "21", "completion_year": 2018, "age_mult": 0.89, "freehold": False},
    # ── District 22 — Jurong / Boon Lay ──────────────────────────────────────
    {"name": "J'Den",                       "district": "22", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "J Gateway",                   "district": "22", "completion_year": 2017, "age_mult": 0.92, "freehold": False},
    {"name": "Lake Grande",                 "district": "22", "completion_year": 2020, "age_mult": 0.88, "freehold": False},
    {"name": "Sora",                        "district": "22", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Ivory Heights",               "district": "22", "completion_year": 1993, "age_mult": 0.55, "freehold": False},
    {"name": "Westmere",                    "district": "22", "completion_year": 1999, "age_mult": 0.65, "freehold": False},
    {"name": "Parc Oasis",                  "district": "22", "completion_year": 1994, "age_mult": 0.60, "freehold": False},
    {"name": "The Lakeshore",               "district": "22", "completion_year": 2008, "age_mult": 0.75, "freehold": False},
    {"name": "Lakeville",                   "district": "22", "completion_year": 2018, "age_mult": 0.85, "freehold": False},
    {"name": "The Lakegarden Residences",   "district": "22", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Luminar Grand (EC)",          "district": "22", "completion_year": None, "age_mult": 1.00, "freehold": False},
    # ── District 23 — Hillview / Bukit Panjang / Choa Chu Kang ──────────────
    {"name": "Hillhaven",                   "district": "23", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Hillock Green",               "district": "23", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "The Myst",                    "district": "23", "completion_year": None, "age_mult": 1.00, "freehold": False},
    {"name": "Kingsford Hillview Peak",     "district": "23", "completion_year": 2016, "age_mult": 0.88, "freehold": False},
    {"name": "The Vales",                   "district": "23", "completion_year": 2018, "age_mult": 0.89, "freehold": False},
    {"name": "Bukit 828",                   "district": "23", "completion_year": 2017, "age_mult": 0.88, "freehold": False},
    {"name": "Hillbrooks",                  "district": "23", "completion_year": 2003, "age_mult": 0.77, "freehold": False},
    # ── District 25 — Kranji / Woodlands ─────────────────────────────────────
    {"name": "Parc Rosewood",               "district": "25", "completion_year": 2014, "age_mult": 0.83, "freehold": False},
    {"name": "Woodhaven",                   "district": "25", "completion_year": 2015, "age_mult": 0.85, "freehold": False},
    {"name": "The Floravale",               "district": "25", "completion_year": 2000, "age_mult": 0.75, "freehold": False},
    {"name": "Rosewood Suites",             "district": "25", "completion_year": 2004, "age_mult": 0.78, "freehold": False},
    # ── District 27 — Yishun / Sembawang ─────────────────────────────────────
    {"name": "Yishun 10 Residences",        "district": "27", "completion_year": 2016, "age_mult": 0.85, "freehold": False},
    {"name": "Eight Courtyards",            "district": "27", "completion_year": 2014, "age_mult": 0.83, "freehold": False},
    {"name": "The Brownstone",              "district": "27", "completion_year": 2018, "age_mult": 0.87, "freehold": False},
    {"name": "NorthPark Residences",        "district": "27", "completion_year": 2017, "age_mult": 0.86, "freehold": False},
    # ── District 28 — Seletar / Punggol North ────────────────────────────────
    {"name": "Park Colonial",               "district": "28", "completion_year": 2021, "age_mult": 0.93, "freehold": False},
    {"name": "The Florence Residences",     "district": "28", "completion_year": 2022, "age_mult": 0.94, "freehold": False},
    {"name": "Riverfront Residences",       "district": "28", "completion_year": 2022, "age_mult": 0.94, "freehold": False},
    {"name": "Affinity at Serangoon",       "district": "28", "completion_year": 2023, "age_mult": 0.96, "freehold": False},
]

# ── Derived lookups built from PROJECT_DATABASE (single source of truth) ──────
_PROJECT_DB_LOOKUP: dict[str, dict] = {p["name"].upper(): p for p in PROJECT_DATABASE}

# DISTRICT_PROFILES derived from PROJECT_DATABASE
DISTRICT_PROFILES: dict[str, dict] = {}
_psf_ranges_by_district = {
    "1":  (2200, 3800), "2":  (2000, 3200), "4":  (2600, 4800),
    "5":  (1700, 2600), "9":  (2800, 4500), "10": (2400, 4200),
    "11": (2000, 3200), "14": (1500, 2100), "15": (1700, 2700),
    "16": (1300, 2000), "18": (1200, 1900), "19": (1200, 1900),
    "20": (1800, 2600), "21": (1700, 2700), "22": (1700, 2700),
    "23": (1400, 2100), "25": (1000, 1600), "27": (1100, 1700),
    "28": (1200, 1800),
}
_fh_ratios_by_district = {
    "1": 0.8, "2": 0.5, "4": 0.6, "5": 0.2, "9": 0.9, "10": 0.9,
    "11": 0.6, "14": 0.3, "15": 0.7, "16": 0.4, "18": 0.0, "19": 0.1,
    "20": 0.2, "21": 0.3, "22": 0.0, "23": 0.1, "25": 0.0, "27": 0.0, "28": 0.1,
}
for _dist in set(p["district"] for p in PROJECT_DATABASE):
    _proj_names = [p["name"] for p in PROJECT_DATABASE if p["district"] == _dist]
    DISTRICT_PROFILES[_dist] = {
        "psf_range": _psf_ranges_by_district.get(_dist, (1200, 2000)),
        "projects": _proj_names,
        "fh_ratio": _fh_ratios_by_district.get(_dist, 0.1),
    }


# ── GLS Site Catalogue ────────────────────────────────────────────────────────
# Real URA Government Land Sales (GLS) tender sites.
# All parameters sourced from official URA tender documents.
# Fields:
#   name          : Site name as published in tender
#   address       : Street / location
#   district      : Postal district (string, matches DISTRICT_MAP)
#   tenure        : As specified in tender — almost always 99-year leasehold for GLS
#   site_area_sqm : Gross site area from tender
#   plot_ratio    : Maximum gross plot ratio from URA Master Plan
#   property_type : Dwelling type mandated by URA zoning
#   permitted_use : Development type permitted under the land use
#   source_year   : Year tender was launched (for reference)
#   notes         : Key planning conditions / remarks

GLS_SITES = [
    {
        "name": "Jurong Lake District (Master Developer Site)",
        "address": "Venture Drive / Jurong Gateway Road, Jurong East",
        "district": "22",
        "tenure": "99-year leasehold",
        "site_area_sqm": 65_000,
        "plot_ratio": 5.6,
        "property_type": "Condominium",
        "permitted_use": ["Residential", "Commercial", "Office"],
        "source_year": 2023,
        "notes": "Mega mixed-use master developer site in Jurong Gateway. Bounded by Boon Lay Way, Venture Drive and Jurong Gateway Road.",
    },
    {
        "name": "Lentor Gardens",
        "address": "Lentor Gardens, Ang Mo Kio",
        "district": "20",
        "tenure": "99-year leasehold",
        "site_area_sqm": 16_789,
        "plot_ratio": 3.0,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2022,
        "notes": "Pure residential site. Part of URA's Lentor precinct, new residential township near Lentor MRT.",
    },
    {
        "name": "Lentor Central (Parcel B)",
        "address": "Lentor Central, Ang Mo Kio",
        "district": "20",
        "tenure": "99-year leasehold",
        "site_area_sqm": 7_585,
        "plot_ratio": 3.0,
        "property_type": "Condominium",
        "permitted_use": ["Residential", "Commercial"],
        "source_year": 2022,
        "notes": "Mixed-use residential with commercial on first storey. Within Lentor precinct.",
    },
    {
        "name": "Tampines Ave 11 (EC)",
        "address": "Tampines Avenue 11, Tampines",
        "district": "18",
        "tenure": "99-year leasehold",
        "site_area_sqm": 22_527,
        "plot_ratio": 2.8,
        "property_type": "Executive Condominium",
        "permitted_use": ["Residential", "Commercial"],
        "source_year": 2022,
        "notes": "Executive Condominium site. EC tenure rules apply (5-year MOP). Commercial component at podium.",
    },
    {
        "name": "Clementi Avenue 1",
        "address": "Clementi Avenue 1, Clementi",
        "district": "5",
        "tenure": "99-year leasehold",
        "site_area_sqm": 16_209,
        "plot_ratio": 2.8,
        "property_type": "Condominium",
        "permitted_use": ["Residential", "Commercial"],
        "source_year": 2023,
        "notes": "Mixed-use residential near Clementi MRT. Commercial component to serve the precinct.",
    },
    {
        "name": "Jalan Tembusu",
        "address": "Jalan Tembusu / Fort Road, East Coast",
        "district": "15",
        "tenure": "99-year leasehold",
        "site_area_sqm": 13_444,
        "plot_ratio": 2.8,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2022,
        "notes": "Pure residential site in sought-after East Coast / Katong area.",
    },
    {
        "name": "Buona Vista Road",
        "address": "Buona Vista Road / North Buona Vista Road",
        "district": "5",
        "tenure": "99-year leasehold",
        "site_area_sqm": 11_767,
        "plot_ratio": 3.0,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2023,
        "notes": "Within the one-north precinct. High amenity catchment from Buona Vista MRT interchange.",
    },
    {
        "name": "Media Circle (Parcel A)",
        "address": "Media Circle, one-north, Buona Vista",
        "district": "5",
        "tenure": "99-year leasehold",
        "site_area_sqm": 14_008,
        "plot_ratio": 3.0,
        "property_type": "Condominium",
        "permitted_use": ["Residential", "Commercial"],
        "source_year": 2023,
        "notes": "Mixed-use site within one-north tech & media hub. Commercial activation required at ground floor.",
    },
    {
        "name": "Hillview Rise",
        "address": "Hillview Rise, Bukit Timah",
        "district": "23",
        "tenure": "99-year leasehold",
        "site_area_sqm": 11_563,
        "plot_ratio": 2.1,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2023,
        "notes": "Hillside residential near HillV2 and Hillview MRT. Constrained height due to surrounding landed estates.",
    },
    {
        "name": "Dunman Road",
        "address": "Dunman Road, East Coast",
        "district": "15",
        "tenure": "99-year leasehold",
        "site_area_sqm": 25_234,
        "plot_ratio": 3.0,
        "property_type": "Condominium",
        "permitted_use": ["Residential", "Commercial"],
        "source_year": 2022,
        "notes": "One of the larger GLS sites in District 15. First storey commercial use to serve surrounding neighbourhood.",
    },
    {
        "name": "Pine Grove (Parcel A)",
        "address": "Pine Grove, Ulu Pandan",
        "district": "21",
        "tenure": "99-year leasehold",
        "site_area_sqm": 21_866,
        "plot_ratio": 2.1,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2023,
        "notes": "Large pure residential site. Low plot ratio reflects landed-character surroundings.",
    },
    {
        "name": "Tengah Garden Avenue (EC)",
        "address": "Tengah Garden Avenue, Tengah",
        "district": "22",
        "tenure": "99-year leasehold",
        "site_area_sqm": 22_020,
        "plot_ratio": 2.8,
        "property_type": "Executive Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2022,
        "notes": "EC site in Tengah, Singapore's newest residential township. Car-lite planning precinct.",
    },
    {
        "name": "Marina Gardens Lane",
        "address": "Marina Gardens Lane, Marina Bay",
        "district": "1",
        "tenure": "99-year leasehold",
        "site_area_sqm": 7_817,
        "plot_ratio": 5.6,
        "property_type": "Condominium",
        "permitted_use": ["Residential", "Commercial"],
        "source_year": 2024,
        "notes": "High-density mixed-use site in Marina Bay. Premium waterfront location. High plot ratio driven by Marina Bay urban design guidelines.",
    },
    {
        "name": "Upper Thomson Road (Parcel B)",
        "address": "Upper Thomson Road, Springleaf",
        "district": "20",
        "tenure": "99-year leasehold",
        "site_area_sqm": 19_517,
        "plot_ratio": 1.4,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2022,
        "notes": "Low-density nature-themed residential site near Springleaf MRT. Plot ratio capped to respect green surroundings.",
    },
    {
        "name": "Senja Close (EC)",
        "address": "Senja Close, Bukit Panjang",
        "district": "23",
        "tenure": "99-year leasehold",
        "site_area_sqm": 18_070,
        "plot_ratio": 2.8,
        "property_type": "Executive Condominium",
        "permitted_use": ["Residential"],
        "source_year": 2024,
        "notes": "EC site in Bukit Panjang, near Segar LRT and Bukit Panjang MRT interchange.",
    },
    # ── Custom / Manual Entry ───────────────────────────────────────────────
    {
        "name": "📝 Custom Site (Manual Entry)",
        "address": "",
        "district": "22",
        "tenure": "99-year leasehold",
        "site_area_sqm": 10_000,
        "plot_ratio": 2.8,
        "property_type": "Condominium",
        "permitted_use": ["Residential"],
        "source_year": None,
        "notes": "Enter site parameters manually for a hypothetical or unlisted GLS site.",
    },
]

FLOOR_RANGES = ["01-05", "06-10", "11-15", "16-20", "21-25", "26-30", "31-35", "36-40"]
PROPERTY_TYPES = ["Condominium", "Apartment", "Executive Condominium"]
SALE_TYPES = ["New Sale", "Resale", "Sub Sale"]

# ── Data Fetching ─────────────────────────────────────────────────────────────

def _generate_mock_transactions(district: str, tenure_filter: str, property_type_filter: str, months: int = 24) -> list[dict]:
    """Generate realistic mock transaction records for a given district."""
    random.seed(42 + int(district))

    profile = DISTRICT_PROFILES.get(district)
    if not profile:
        return []

    psf_min, psf_max = profile["psf_range"]
    transactions = []
    n = random.randint(35, 80)

    end_date = datetime(2026, 6, 1)

    for _ in range(n):
        # Random date in the past `months`
        days_back = random.randint(0, months * 30)
        tx_date = end_date - timedelta(days=days_back)
        contract_date = tx_date.strftime("%y%m")

        # Property type
        ptype = property_type_filter if property_type_filter != "All" else random.choice(PROPERTY_TYPES)
        if property_type_filter != "All":
            if "condo" in property_type_filter.lower() or "apartment" in property_type_filter.lower():
                ptype = random.choices(["Condominium", "Apartment"], weights=[70, 30])[0]

        # Tenure
        is_fh = random.random() < profile["fh_ratio"]
        if tenure_filter == "Freehold":
            is_fh = True
        elif tenure_filter == "99-year leasehold":
            is_fh = False
        tenure_str = "Freehold" if is_fh else "99 yrs lease commencing from 2020"

        # Size
        if ptype == "Executive Condominium":
            size_sqm = random.randint(80, 160)
        else:
            size_sqm = random.randint(40, 180)
        size_sqft = round(size_sqm * 10.764)

        # Floor
        floor = random.choice(FLOOR_RANGES)
        floor_num = int(floor.split("-")[0])
        floor_premium = floor_num * 0.004  # ~0.4% per floor band

        project = random.choice(profile["projects"])
        proj_upper = project.upper()

        # Determine sale type and age multiplier from the single PROJECT_DATABASE source of truth
        proj_entry = _PROJECT_DB_LOOKUP.get(proj_upper, {})
        is_buc = proj_entry.get("completion_year") is None
        age_multiplier = proj_entry.get("age_mult", 1.0)
        sale_type = "New Sale" if is_buc else "Resale"

        # PSF — freehold premium + floor premium + random noise
        fh_premium = 0.15 if is_fh else 0.0
        base_psf = random.uniform(psf_min, psf_max)

        psf = round(base_psf * (1 + fh_premium + floor_premium) * age_multiplier, 0)
        price = round((psf * size_sqft) / 1000) * 1000

        transactions.append({
            "project": project,
            "street": f"District {district}",
            "area": str(size_sqm),
            "floorRange": floor,
            "contractDate": contract_date,
            "typeOfSale": sale_type,
            "price": str(price),
            "propertyType": ptype,
            "district": district,
            "typeOfArea": "Strata",
            "tenure": tenure_str,
        })

    return transactions


def _parse_transactions(raw: list[dict]) -> list[dict]:
    """Parse and enrich raw URA transaction records."""
    parsed = []
    for r in raw:
        try:
            size_sqm = float(r.get("area", 0))
            size_sqft = round(size_sqm * 10.764, 0)
            price = float(r.get("price", 0))
            psf = round(price / size_sqft, 0) if size_sqft > 0 else None
            psm = round(price / size_sqm, 0) if size_sqm > 0 else None

            # Parse date: URA API format is MMYY, mock generator is YYMM. Parse both.
            date_str = r.get("contractDate", "")
            if len(date_str) == 4:
                val1 = int(date_str[:2])
                val2 = int(date_str[2:])
                # Check which one is a valid month (1-12). Prioritize MMYY (val1 as month) for API.
                if 1 <= val1 <= 12:
                    month = val1
                    year = 2000 + val2
                elif 1 <= val2 <= 12:
                    month = val2
                    year = 2000 + val1
                else:
                    raise ValueError("Invalid month in contractDate")
                tx_date = datetime(year, month, 1)
                quarter = f"Q{((month - 1) // 3) + 1} {year}"
            else:
                tx_date = None
                quarter = "Unknown"

            parsed.append({
                "project":       r.get("project", "Unknown"),
                "district":      r.get("district", ""),
                "floor":         r.get("floorRange", ""),
                "size_sqm":      size_sqm,
                "size_sqft":     size_sqft,
                "price_sgd":     price,
                "psf":           psf,
                "psm":           psm,
                "type_of_sale":  r.get("typeOfSale", ""),
                "property_type": r.get("propertyType", ""),
                "tenure":        r.get("tenure", ""),
                "date":          tx_date,
                "quarter":       quarter,
            })
        except Exception:
            continue
    return parsed


def is_comparable_property_type(selected: str, transaction: str) -> bool:
    """
    Determines if a transaction property type is comparable to the selected zoning type.
    Treats 'Condominium' and 'Apartment' as comparable private non-landed residential,
    but keeps 'Executive Condominium' separate.
    """
    s_clean = selected.lower().strip()
    t_clean = transaction.lower().strip()
    
    if "executive" in s_clean or "executive" in t_clean:
        return "executive" in s_clean and "executive" in t_clean
        
    if "condo" in s_clean or "apartment" in s_clean:
        return "condo" in t_clean or "apartment" in t_clean
        
    return s_clean in t_clean or t_clean in s_clean


@st.cache_data
def get_transactions(district: str, tenure: str, property_type: str) -> list[dict]:
    """
    Fetch and parse transaction records for the given criteria.

    Attempts live URA API if URA_ACCESS_KEY is configured.
    Falls back to realistic mock data otherwise.
    """
    if URA_ACCESS_KEY:
        try:
            return _fetch_live(district, tenure, property_type)
        except Exception as e:
            print(f"URA API error: {e}. Falling back to mock data.")

    raw = _generate_mock_transactions(district, tenure, property_type)
    return _parse_transactions(raw)


def _fetch_live(district: str, tenure: str, property_type: str) -> list[dict]:
    """Fetch live data from URA Data Service API using v1 endpoints."""
    if not URA_ACCESS_KEY:
        raise ValueError("URA_ACCESS_KEY is not configured")

    headers = {
        "AccessKey": URA_ACCESS_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Step 1: Generate daily token
    token_url = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
    token_resp = requests.get(token_url, headers=headers, timeout=15)
    token_resp.raise_for_status()
    token_data = token_resp.json()
    if token_data.get("Status") != "Success":
        raise ValueError(f"Failed to generate URA token: {token_data.get('Message')}")
    token = token_data.get("Result")
    if not token:
        raise ValueError("No token returned in URA response")

    # Step 2: Fetch transaction batches
    headers["Token"] = token
    
    raw_txns = []
    district_padded = district.zfill(2)

    sale_type_map = {
        "1": "New Sale",
        "2": "Sub Sale",
        "3": "Resale"
    }

    # Map district to URA batch (Batch 1: 01-07, Batch 2: 08-14, Batch 3: 15-21, Batch 4: 22-28)
    try:
        dist_num = int(district)
    except ValueError:
        dist_num = 22

    if 1 <= dist_num <= 7:
        target_batch = 1
    elif 8 <= dist_num <= 14:
        target_batch = 2
    elif 15 <= dist_num <= 21:
        target_batch = 3
    elif 22 <= dist_num <= 28:
        target_batch = 4
    else:
        target_batch = 1

    url = f"https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1?service=PMI_Resi_Transaction&batch={target_batch}"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("Status") == "Success":
            results = data.get("Result", [])
            for proj in results:
                project_name = proj.get("project", "Unknown")
                street_name = proj.get("street", "")
                for tx in proj.get("transaction", []):
                    # Filter by district first to save parsing overhead
                    tx_dist = str(tx.get("district", "")).strip()
                    if tx_dist.startswith("0") and len(tx_dist) > 1:
                        tx_dist_clean = tx_dist[1:]
                    else:
                        tx_dist_clean = tx_dist
                    
                    if tx_dist_clean != district and tx_dist != district_padded:
                        continue

                    # Map typeOfSale code to string
                    tos_code = str(tx.get("typeOfSale", ""))
                    sale_type = sale_type_map.get(tos_code, tos_code)

                    # Property type filter using comparability helper
                    tx_ptype = tx.get("propertyType", "")
                    if property_type != "All" and not is_comparable_property_type(property_type, tx_ptype):
                        continue

                    # Tenure filter
                    tenure_str = tx.get("tenure", "").lower()
                    if tenure == "Freehold" and "freehold" not in tenure_str:
                        continue
                    if tenure == "99-year leasehold" and "99" not in tenure_str:
                        continue

                    # Flatten record for parsing
                    raw_txns.append({
                        "project": project_name,
                        "street": street_name,
                        "area": tx.get("area"),
                        "floorRange": tx.get("floorRange"),
                        "contractDate": tx.get("contractDate"),
                        "typeOfSale": sale_type,
                        "price": tx.get("price"),
                        "propertyType": tx_ptype,
                        "district": district,
                        "typeOfArea": tx.get("typeOfArea"),
                        "tenure": tx.get("tenure"),
                    })
    except Exception as e:
        print(f"Error fetching batch {target_batch}: {e}")

    return _parse_transactions(raw_txns)


def load_realis_csv(file_like) -> list[dict]:
    """Parse URA REALIS transaction records from an uploaded CSV file."""
    try:
        # Load the CSV
        df = pd.read_csv(file_like)
        
        # Clean up columns: strip spaces and convert to lowercase
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # If the first few rows are empty or metadata, let's find the header row.
        # REALIS CSVs sometimes have title rows like "Private Residential Property Transactions..."
        header_row_idx = None
        for idx in range(min(15, len(df))):
            row_vals = [str(val).strip().lower() for val in df.iloc[idx].values]
            if any("project name" in val or "project" in val or "transacted price" in val or "price ($)" in val for val in row_vals):
                header_row_idx = idx
                break
                
        if header_row_idx is not None:
            # Re-read with the correct header
            if hasattr(file_like, 'seek'):
                file_like.seek(0)
            df = pd.read_csv(file_like, skiprows=header_row_idx + 1)
            df.columns = [str(col).strip().lower() for col in df.columns]
            
        # Map columns
        col_mapping = {
            'project': ['project name', 'project', 'property name'],
            'district': ['postal district', 'district', 'd'],
            'floor': ['floor level', 'floor range', 'storey range', 'floor'],
            'size_sqm': ['area (sqm)', 'size (sqm)', 'area sqm', 'sqm'],
            'size_sqft': ['area (sqft)', 'size (sqft)', 'area sqft', 'sqft'],
            'price_sgd': ['transacted price ($)', 'price ($)', 'price', 'transacted price'],
            'psf': ['unit price ($ psf)', 'psf', 'unit price psf', 'price psf'],
            'psm': ['unit price ($ psm)', 'psm', 'unit price psm', 'price psm'],
            'type_of_sale': ['type of sale', 'sale type', 'type of transaction'],
            'property_type': ['property type', 'type'],
            'tenure': ['tenure'],
            'date': ['date of sale', 'sale date', 'contract date', 'date']
        }
        
        mapped_df = pd.DataFrame()
        for key, aliases in col_mapping.items():
            for alias in aliases:
                if alias in df.columns:
                    mapped_df[key] = df[alias]
                    break
            if key not in mapped_df.columns:
                mapped_df[key] = None
                
        parsed = []
        for _, row in mapped_df.iterrows():
            try:
                # project
                proj_name = str(row['project']) if not pd.isna(row['project']) else "Unknown"
                if proj_name.lower() in ("nan", "none", ""):
                    proj_name = "Unknown"
                    
                # size_sqm
                sz_sqm = row['size_sqm']
                if pd.isna(sz_sqm) or sz_sqm is None:
                    sz_sqm = 0
                else:
                    sz_sqm = float(str(sz_sqm).replace(',', '').strip())
                    
                # size_sqft
                sz_sqft = row['size_sqft']
                if pd.isna(sz_sqft) or sz_sqft is None:
                    sz_sqft = round(sz_sqm * 10.764, 0)
                else:
                    sz_sqft = float(str(sz_sqft).replace(',', '').strip())
                    
                # price
                pr = row['price_sgd']
                if pd.isna(pr) or pr is None:
                    continue
                pr = float(str(pr).replace('$', '').replace(',', '').strip())
                
                # psf
                p_psf = row['psf']
                if pd.isna(p_psf) or p_psf is None:
                    p_psf = round(pr / sz_sqft, 0) if sz_sqft > 0 else 0
                else:
                    p_psf = float(str(p_psf).replace('$', '').replace(',', '').strip())
                    
                # psm
                p_psm = row['psm']
                if pd.isna(p_psm) or p_psm is None:
                    p_psm = round(pr / sz_sqm, 0) if sz_sqm > 0 else 0
                else:
                    p_psm = float(str(p_psm).replace('$', '').replace(',', '').strip())
                    
                # district
                dist = str(row['district']) if not pd.isna(row['district']) else ""
                dist = dist.lower().replace('d', '').strip()
                # Remove decimal part if float got converted to string (e.g. "22.0")
                if '.' in dist:
                    dist = dist.split('.')[0]
                if dist.startswith('0') and len(dist) > 1:
                    dist = dist[1:]
                
                # date
                dt_val = row['date']
                tx_date = None
                quarter = "Unknown"
                if not pd.isna(dt_val) and dt_val is not None:
                    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%y%m", "%b-%y", "%b-%Y"):
                        try:
                            tx_date = datetime.strptime(str(dt_val).strip(), fmt)
                            month = tx_date.month
                            year = tx_date.year
                            quarter = f"Q{((month - 1) // 3) + 1} {year}"
                            break
                        except Exception:
                            continue
                            
                parsed.append({
                    "project":       proj_name,
                    "district":      dist,
                    "floor":         str(row['floor']) if not pd.isna(row['floor']) else "",
                    "size_sqm":      sz_sqm,
                    "size_sqft":     sz_sqft,
                    "price_sgd":     pr,
                    "psf":           p_psf,
                    "psm":           p_psm,
                    "type_of_sale":  str(row['type_of_sale']) if not pd.isna(row['type_of_sale']) else "",
                    "property_type": str(row['property_type']) if not pd.isna(row['property_type']) else "",
                    "tenure":        str(row['tenure']) if not pd.isna(row['tenure']) else "",
                    "date":          tx_date,
                    "quarter":       quarter,
                })
            except Exception:
                continue
        return parsed
    except Exception as e:
        print(f"Error loading REALIS CSV: {e}")
        return []
