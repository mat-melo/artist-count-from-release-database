# =============================================================================
# IMPORTS AND DATA LOCATION
# =============================================================================
from pathlib import Path
import re
import numpy as np
import pandas as pd
import country_converter as coco
import seaborn.objects as so
from seaborn import axes_style


def find_csv(name="official_releases.csv"):
    """Search /kaggle/input first (any mount path), then the working folder."""
    for root in (Path("/kaggle/input"), Path(".")):
        if not root.exists():
            continue
        hits = sorted(p for p in root.rglob(name) if p.is_file())
        if hits:
            return hits[0]
    raise FileNotFoundError(name)

# Locate the source CSV and report its path
CSV = find_csv()
print("reading", CSV)


# =============================================================================
# LOAD DATA
# =============================================================================
# Read only the three needed columns as strings, then coerce the year to numeric
f_df = pd.read_csv(CSV, dtype=str, keep_default_na=False,
                 usecols=["artist_name", "date_year", "country_code"])
f_df["year"] = pd.to_numeric(f_df["date_year"], errors="coerce")


# =============================================================================
# MAIN FILTERS
# =============================================================================
# 1) Keep only releases from 1950–2025 (recommended coverage window)
f_df = f_df[f_df["year"].between(1950, 2025)]
# 2) Drop rows with invalid / non-country ISO2 codes (worldwide, regions, historic states)
f_df = f_df[~f_df["country_code"].isin(["XW", "XE", "", "XZ", "XC", "SU", "CS", "AN", "YU", "XG"] + [None])]
# 3) Drop placeholder / broken artist names
f_df = f_df[~f_df["artist_name"].isin(["Various Artists", "", "[unknown]", "[dialogue]", "[no artist]"] + [None])]
# 4) Drop artist names made only of digits (keep names with symbols/letters)
f_df = f_df[~f_df["artist_name"].str.fullmatch(r"\d+").fillna(False)]


# =============================================================================
# STEP 1: DEBUT YEAR PER ARTIST
# =============================================================================
# For each artist, find the earliest release year = the artist's debut year
debut_year = (
    f_df.groupby("artist_name")["year"]
      .min()
      .reset_index()
      .rename(columns={"year": "debut_year"})
)


# =============================================================================
# STEP 2: KEEP ONLY DEBUT-YEAR RELEASES AND BUILD COUNTRY CANDIDATES
# =============================================================================
# Merge debut year back into the main table
df_debut = f_df.merge(debut_year, on="artist_name")
# Keep only rows where the release year equals the artist's debut year
df_debut = df_debut[df_debut["year"] == df_debut["debut_year"]]
# Unique (artist, country) pairs observed in the debut year
debut_countries = df_debut[["artist_name", "country_code"]].drop_duplicates()


# =============================================================================
# STEP 3: COUNT RELEASES PER (ARTIST, COUNTRY) IN THE DEBUT YEAR
# =============================================================================
# Used later to break ties when an artist debuts in multiple countries
total_per_country = (
    df_debut.groupby(["artist_name", "country_code"])
      .size()
      .reset_index(name="total_releases")
)


# =============================================================================
# STEP 4: ASSIGN A SINGLE DEBUT COUNTRY PER ARTIST
# =============================================================================
# If an artist has multiple debut countries in the same year:
#   - pick the country with the most releases that year
#   - break ties alphabetically by country code
country_choice = (
    debut_countries
      .merge(total_per_country, on=["artist_name", "country_code"], how="left")
      .sort_values(
          ["artist_name", "total_releases", "country_code"],
          ascending=[True, False, True]
      )
      .drop_duplicates("artist_name", keep="first")
      .rename(columns={"country_code": "debut_country"})
      [["artist_name", "debut_country"]]
)


# =============================================================================
# STEP 5: COUNTRY-YEAR COUNTS OF NEW ARTISTS
# =============================================================================
# Attach the chosen debut country to each artist and count new artists per country-year
debut_count = debut_year.merge(country_choice, on="artist_name")

debut_count = (
    debut_count
      .groupby(["debut_country", "debut_year"])
      .size()
      .reset_index(name="debuting_artists")
      .rename(columns={"debut_country": "country_code", "debut_year": "year"})
      .sort_values(["year", "country_code"])
      .reset_index(drop=True)
)


# =============================================================================
# STEP 6: ADD COUNTRY NAMES AND SAVE
# =============================================================================
cc = coco.CountryConverter()

# Convert ISO2 codes to short country names
debut_count["country_name"] = cc.convert(
    names=debut_count["country_code"], 
    src="ISO2", 
    to="name_short"
)

# Persist the country-year table for reuse / Tableau
debut_count.to_csv("artist_debut_per_country_per_year.csv", index=False)


# =============================================================================
# EXPLORATORY PLOTS: TOP COUNTRIES
# =============================================================================
# Keep only countries whose average annual debuts >= 132
# (i.e. the largest / most consistent music markets) to reduce clutter
x = 132
country_average = (
    debut_count
      .groupby("country_name")["debuting_artists"]
      .mean()
)

valid_countries = country_average[country_average >= x].index

debut_count_plot = debut_count[
    debut_count["country_name"].isin(valid_countries)
].reset_index(drop=True)

# Line plot of new artists per year for the top countries
so.Plot(debut_count_plot, x="year", y="debuting_artists", color="country_name").add(so.Line()).theme(axes_style("whitegrid"))

# Stacked/overlapping area plot for a cumulative view of the same data
so.Plot(debut_count_plot, x="year", y="debuting_artists", color="country_name").add(so.Area(edgewidth=.2, alpha=.6)).theme(axes_style("white"))


# =============================================================================
# LAST 20 YEARS: RECENT TREND
# =============================================================================
# Restrict the plot data to 2005–2025 to inspect recent dynamics
debut_count_plot2 = debut_count_plot[
    debut_count_plot["year"].between(2005, 2025)
].reset_index(drop=True)

so.Plot(debut_count_plot2, x="year", y="debuting_artists", color="country_name").add(so.Line()).theme(axes_style("whitegrid"))


# =============================================================================
# PERCENTAGE VARIATION BETWEEN FIRST AND LAST YEAR OF THE 20-YEAR WINDOW
# =============================================================================
# Sum debuts in the first year (2005) of the window per country
debuting_before = (
    debut_count_plot2.loc[debut_count_plot2["year"] == debut_count_plot2["year"].min()]
    .groupby("country_name")["debuting_artists"]
    .sum()
    .rename("debuting_before")
)

# Sum debuts in the last year (2025) of the window per country
debuting_after = (
    debut_count_plot2.loc[debut_count_plot2["year"] == debut_count_plot2["year"].max()]
    .groupby("country_name")["debuting_artists"]
    .sum()
    .rename("debuting_after")
)

# Join the two years side by side (drop countries missing either year)
comparison = pd.concat([debuting_before, debuting_after], axis=1).dropna()

# Percent change in debuting artists from 2005 to 2025
comparison["pct_variation"] = (
    (comparison["debuting_after"] - comparison["debuting_before"])
    / comparison["debuting_before"] * 100
)

# Final tidy table sorted from largest decline to largest growth
debut_count_var = (
    comparison[["pct_variation"]]
    .reset_index()
    .rename(columns={"country": "country", "pct_variation": "pct_variation"})
    .sort_values("pct_variation")
    .reset_index(drop=True)
)

debut_count_var
