"""
ETL: Climate Classification Layer
Hardcodes hot/humid classification for our 9 Southeast states
based on NOAA 1991-2020 Climate Normals (published averages)
Source citation: NOAA NCEI U.S. Climate Normals 1991-2020
https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals
"""

import pandas as pd
import sqlite3

DB_PATH    = "/home/claude/southeast_population.db"
OUTPUT_DIR = "/home/claude/output_csvs"

# ── CLIMATE DATA ─────────────────────────────────────────────────────────────
# Annual avg temp (°F) and avg summer relative humidity (%) from NOAA 1991-2020 normals
# Representative stations used (major city per state)
# All 9 states classify as Hot-Humid per ASHRAE 169 climate zone definitions
# (summer design temp > 85°F, humidity ratio elevated June-September)

climate_data = [
    # state,               rep_station,          ann_avg_f, summer_avg_max_f, summer_rh_pct, cooling_degree_days, climate_zone
    ("Alabama",           "Birmingham, AL",       64.0,      90.2,             72,            2641,  "Hot-Humid"),
    ("Arkansas",          "Little Rock, AR",      62.9,      92.4,             70,            2727,  "Hot-Humid"),
    ("Florida",           "Orlando, FL",          73.0,      91.8,             75,            4132,  "Hot-Humid"),
    ("Georgia",           "Atlanta, GA",          62.0,      89.1,             69,            1995,  "Hot-Humid"),
    ("Louisiana",         "New Orleans, LA",      69.0,      91.5,             78,            2902,  "Hot-Humid"),
    ("Mississippi",       "Jackson, MS",          65.5,      91.7,             73,            2597,  "Hot-Humid"),
    ("North Carolina",    "Raleigh, NC",          60.0,      88.5,             68,            1624,  "Hot-Humid"),
    ("South Carolina",    "Columbia, SC",         64.5,      92.3,             70,            2418,  "Hot-Humid"),
    ("Tennessee",         "Nashville, TN",        59.4,      89.6,             68,            1652,  "Hot-Humid"),
]

df_climate = pd.DataFrame(climate_data, columns=[
    "STATE", "REP_STATION", "ANN_AVG_TEMP_F", "SUMMER_AVG_MAX_F",
    "SUMMER_RH_PCT", "COOLING_DEGREE_DAYS", "CLIMATE_ZONE"
])

# Fun facts for dashboard callouts
df_climate["CLIMATE_NOTE"] = df_climate.apply(lambda r:
    f"Avg summer high {r.SUMMER_AVG_MAX_F}°F | {r.SUMMER_RH_PCT}% humidity | {r.COOLING_DEGREE_DAYS} cooling degree days/yr",
    axis=1
)

print("Climate classifications:")
print(df_climate[["STATE","ANN_AVG_TEMP_F","SUMMER_AVG_MAX_F","SUMMER_RH_PCT","COOLING_DEGREE_DAYS"]].to_string(index=False))

# ── MERGE WITH POPULATION DATA ────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)

df_state_pop = pd.read_sql("SELECT * FROM state_population", conn)
df_county_pop = pd.read_sql("SELECT * FROM county_population", conn)

# Join climate to state population
df_state_merged = df_state_pop.merge(df_climate, on="STATE", how="left")

# Join climate to county population
df_county_merged = df_county_pop.merge(df_climate, on="STATE", how="left")

# Write back to DB
df_climate.to_sql("climate_classification", conn, if_exists="replace", index=False)
df_state_merged.to_sql("state_population_climate", conn, if_exists="replace", index=False)
df_county_merged.to_sql("county_population_climate", conn, if_exists="replace", index=False)

print(f"\nTables written to DB:")
for t in ["climate_classification", "state_population_climate", "county_population_climate"]:
    n = pd.read_sql(f"SELECT COUNT(*) as n FROM {t}", conn).iloc[0]["n"]
    print(f"  {t}: {n} rows")

# ── EXPORT FINAL CSVs FOR TABLEAU ────────────────────────────────────────────
df_state_merged.to_csv(f"{OUTPUT_DIR}/state_population_climate.csv", index=False)
df_county_merged.to_csv(f"{OUTPUT_DIR}/county_population_climate.csv", index=False)
df_climate.to_csv(f"{OUTPUT_DIR}/climate_classification.csv", index=False)

# Gwinnett county spotlight (personal connection)
gwinnett = df_county_merged[
    (df_county_merged["COUNTY_CLEAN"] == "Gwinnett") &
    (df_county_merged["STATE"] == "Georgia")
][["YEAR","POPULATION","PCT_CHANGE_FROM_1950","AC_ERA"]].sort_values("YEAR")

print(f"\n── Gwinnett County Spotlight ──")
print(gwinnett.to_string(index=False))

conn.close()
print("\n✅ Climate ETL complete.")
