"""
ETL: Southeast Population & Air Conditioning Project
Source: NHGIS A00 Total Population Time Series (County Level)
Output: SQLite DB + cleaned CSVs for Tableau
"""

import pandas as pd
import sqlite3
import os

# ── CONFIG ───────────────────────────────────────────────────────────────────
INPUT_FILE = "/mnt/user-data/uploads/nhgis0001_ts_nominal_county.csv"
DB_PATH    = "/home/claude/southeast_population.db"
OUTPUT_DIR = "/home/claude/output_csvs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_STATES = [
    "Alabama", "Arkansas", "Florida", "Georgia", "Louisiana",
    "Mississippi", "North Carolina", "South Carolina", "Tennessee"
]

# Year columns we care about — 1900 onward gives us solid coverage
# We'll keep all years but flag pre-1900 as sparse
YEAR_COLS = {
    "A00AA1790": 1790, "A00AA1800": 1800, "A00AA1810": 1810,
    "A00AA1820": 1820, "A00AA1830": 1830, "A00AA1840": 1840,
    "A00AA1850": 1850, "A00AA1860": 1860, "A00AA1870": 1870,
    "A00AA1880": 1880, "A00AA1890": 1890, "A00AA1900": 1900,
    "A00AA1910": 1910, "A00AA1920": 1920, "A00AA1930": 1930,
    "A00AA1940": 1940, "A00AA1950": 1950, "A00AA1960": 1960,
    "A00AA1970": 1970, "A00AA1980": 1980, "A00AA1990": 1990,
    "A00AA2000": 2000, "A00AA2010": 2010, "A00AA2020": 2020
}

# ── STEP 1: LOAD & FILTER ────────────────────────────────────────────────────
print("Loading raw data...")
df_raw = pd.read_csv(INPUT_FILE)
print(f"  Raw rows: {len(df_raw)}")

df = df_raw[df_raw["STATE"].isin(TARGET_STATES)].copy()
print(f"  After state filter: {len(df)} rows ({df['STATE'].nunique()} states)")

# ── STEP 2: CLEAN WIDE FORMAT ────────────────────────────────────────────────
# Keep only the columns we need
keep_cols = ["GISJOIN", "STATE", "STATEFP", "COUNTY", "COUNTYFP"] + list(YEAR_COLS.keys())
df = df[keep_cols].copy()

# Rename year columns to plain years
df.rename(columns=YEAR_COLS, inplace=True)

# Clean up county name (strip " County" suffix for cleaner display)
df["COUNTY_CLEAN"] = df["COUNTY"].str.replace(" County", "", regex=False).str.strip()

# State FIPS as zero-padded string
df["STATEFP"] = df["STATEFP"].astype(str).str.zfill(2)
df["COUNTYFP"] = df["COUNTYFP"].astype(str).str.zfill(3)
df["FIPS"] = df["STATEFP"] + df["COUNTYFP"]

print(f"\nColumn check:")
print(f"  States: {sorted(df['STATE'].unique())}")
print(f"  Counties total: {len(df)}")

# ── STEP 3: MELT TO LONG FORMAT ──────────────────────────────────────────────
# Wide = one row per county, columns = years
# Long = one row per county per year (better for Tableau)
id_cols = ["GISJOIN", "FIPS", "STATE", "STATEFP", "COUNTY", "COUNTY_CLEAN", "COUNTYFP"]
year_cols = list(YEAR_COLS.values())

df_long = df.melt(
    id_vars=id_cols,
    value_vars=year_cols,
    var_name="YEAR",
    value_name="POPULATION"
)
df_long["YEAR"] = df_long["YEAR"].astype(int)

# Flag data quality
df_long["DATA_SPARSE"] = df_long["YEAR"] < 1900  # pre-1900 has many nulls

# AC era flag — window units took off ~1950, central AC standard by 1970
df_long["AC_ERA"] = df_long["YEAR"].apply(
    lambda y: "Pre-AC" if y < 1950 else ("Early AC" if y < 1970 else "AC Era")
)

# Drop rows where population is null (historical ghost counties)
df_long_clean = df_long.dropna(subset=["POPULATION"]).copy()
df_long_clean["POPULATION"] = df_long_clean["POPULATION"].astype(int)

print(f"\nLong format rows (with data): {len(df_long_clean)}")
print(f"Long format rows (nulls dropped): {len(df_long) - len(df_long_clean)} removed")

# ── STEP 4: STATE-LEVEL AGGREGATION ──────────────────────────────────────────
df_state = df_long_clean.groupby(["STATE", "STATEFP", "YEAR", "AC_ERA"])["POPULATION"].sum().reset_index()
df_state.rename(columns={"POPULATION": "STATE_POPULATION"}, inplace=True)
print(f"\nState-level rows: {len(df_state)}")

# ── STEP 5: GROWTH METRICS ───────────────────────────────────────────────────
# County-level: population change since 1950 (AC baseline)
baseline_1950 = df_long_clean[df_long_clean["YEAR"] == 1950][["FIPS", "POPULATION"]].rename(
    columns={"POPULATION": "POP_1950"}
)
df_long_clean = df_long_clean.merge(baseline_1950, on="FIPS", how="left")
df_long_clean["POP_CHANGE_FROM_1950"] = df_long_clean["POPULATION"] - df_long_clean["POP_1950"]
df_long_clean["PCT_CHANGE_FROM_1950"] = (
    (df_long_clean["POPULATION"] - df_long_clean["POP_1950"]) / df_long_clean["POP_1950"] * 100
).round(2)

# State-level: same
baseline_state_1950 = df_state[df_state["YEAR"] == 1950][["STATE", "STATE_POPULATION"]].rename(
    columns={"STATE_POPULATION": "POP_1950"}
)
df_state = df_state.merge(baseline_state_1950, on="STATE", how="left")
df_state["PCT_CHANGE_FROM_1950"] = (
    (df_state["STATE_POPULATION"] - df_state["POP_1950"]) / df_state["POP_1950"] * 100
).round(2)

# ── STEP 6: SQLITE ───────────────────────────────────────────────────────────
print(f"\nWriting to SQLite: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)

df_long_clean.to_sql("county_population", conn, if_exists="replace", index=False)
df_state.to_sql("state_population", conn, if_exists="replace", index=False)
df[id_cols + list(YEAR_COLS.values())].to_sql("county_wide", conn, if_exists="replace", index=False)

# Verify
for table in ["county_population", "state_population", "county_wide"]:
    count = pd.read_sql(f"SELECT COUNT(*) as n FROM {table}", conn).iloc[0]["n"]
    print(f"  {table}: {count} rows")

conn.close()

# ── STEP 7: EXPORT CSVs ──────────────────────────────────────────────────────
print(f"\nExporting CSVs to {OUTPUT_DIR}...")

df_long_clean.to_csv(f"{OUTPUT_DIR}/county_population_long.csv", index=False)
df_state.to_csv(f"{OUTPUT_DIR}/state_population_long.csv", index=False)

# Also export a 2020 snapshot for map views
snap_2020 = df_long_clean[df_long_clean["YEAR"] == 2020][
    ["FIPS", "STATE", "COUNTY_CLEAN", "POPULATION", "POP_1950", "POP_CHANGE_FROM_1950", "PCT_CHANGE_FROM_1950"]
].copy()
snap_2020.to_csv(f"{OUTPUT_DIR}/county_2020_snapshot.csv", index=False)

print(f"  county_population_long.csv — {len(df_long_clean)} rows")
print(f"  state_population_long.csv  — {len(df_state)} rows")
print(f"  county_2020_snapshot.csv   — {len(snap_2020)} rows")

print("\n✅ ETL complete.")
