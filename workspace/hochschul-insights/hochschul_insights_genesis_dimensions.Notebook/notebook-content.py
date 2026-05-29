# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "__LAKEHOUSE_ID__",
# META       "default_lakehouse_name": "hochschul_insights_lh",
# META       "default_lakehouse_workspace_id": "__WORKSPACE_ID__",
# META       "known_lakehouses": [
# META         {
# META           "id": "__LAKEHOUSE_ID__"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Hochschul-Insights — GENESIS Dimensions
# 
# Builds dimension tables from the fact tables landed by the **GENESIS Loader** notebook. Run this *after* all 10 fact loaders have finished (the Fabric pipeline wires this dependency automatically).
# 
# ## Dimensions built
# 
# | Lakehouse table         | Built from                              |
# |-------------------------|------------------------------------------|
# | Genesis.Hochschulen   | Studierende + Wikidata + city fallback |
# | Genesis.Bundesland    | DISTINCT across Bundesland-facts         |
# | Genesis.Hochschulart  | DISTINCT across Ausgaben/Einnahmen/Drittmittel |
# | Genesis.Faechergruppe | DISTINCT across Finanzen + Professoren   |
# | Genesis.Geschlecht    | DISTINCT across all Personen-facts       |
# | Genesis.Nationalitaet | DISTINCT across Studierende-facts        |
# 
# Also drops the Hochschule name column from Genesis.Studierende (the name now lives only on the dim, joined via Hochschule_Code).

# MARKDOWN ********************

# ## 1. Configuration

# CELL ********************

LAKEHOUSE_SCHEMA = "Genesis"
import pandas as pd
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {LAKEHOUSE_SCHEMA}")
print(f"Schema ready: {LAKEHOUSE_SCHEMA}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Hochschule dimension (Genesis.Hochschulen)
# 
# Builds an EF1-keyed Hochschule dimension from Genesis.Studierende and enriches it with geographic coordinates, city, and Bundesland.
# 
# **Resolution flow:**
# 
# 1. **Source C — curated EF1 → Wikidata QID mapping** (preferred). Hand-curated dict (`CURATED_EF1_TO_QID`).
# 2. **Source A — Wikidata SPARQL with name match.** Normalized name match, fuzzy with `get_close_matches` cutoff 0.85.
# 3. **Source City — city name from GENESIS Hochschule name.** Strip noise words and match against German cities >20k pop on Wikidata. Sets Lat/Lon/Stadt/Bundesland from the city.
# 4. **Reverse geocode** — for any row that has Lat/Lon but no Stadt yet, find the nearest German city within 30 km and use its name + Bundesland.
# 5. **Bundesland coalesce** — any still-missing Bundesland is filled from the resolved Stadt's Bundesland.

# CELL ********************

import re
import unicodedata
import requests
import json
from difflib import get_close_matches

# ---- CURATED OVERRIDES (Option C — preferred) ----------------------------
# Add EF1 -> Wikidata QID pairs here whenever the SPARQL fuzzy match (Option A)
# misses or wrong-matches a Hochschule. Re-run this cell to refresh.
# Find QID by searching wikidata.org for the Hochschule and copying the Qxxxxx.
CURATED_EF1_TO_QID = {
    # "0001": "Q55044",   # Universität Hamburg
}
# --------------------------------------------------------------------------

# ---- MANUAL Hochschule name -> (Stadt, Bundesland) overrides --------------
# Highest-priority Stadt/Bundesland source. Wins over Wikidata + city heuristic.
# Loaded from CSV in lakehouse Files/. Edit the CSV (semicolon-separated:
#   Hochschule_Name_GENESIS;Stadt;Bundesland) and re-run the notebook.
_MAPPING_URL = "https://raw.githubusercontent.com/KornAlexander/Fabric-Demos/main/Hochschul-Insights/files/hochschule_city_mapping.csv"
_mapping_df = pd.read_csv(_MAPPING_URL, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
print(f"CSV columns: {list(_mapping_df.columns)}; rows: {len(_mapping_df)}")
MANUAL_NAME_TO_CITY = {
    row["Hochschule_Name_GENESIS"]: (row["Stadt"], row["Bundesland"])
    for _, row in _mapping_df.iterrows()
    if row["Hochschule_Name_GENESIS"]
}
print(f"MANUAL_NAME_TO_CITY: loaded {len(MANUAL_NAME_TO_CITY)} entries from CSV")
# --------------------------------------------------------------------------

# 1. Distinct Hochschulen — try fact tables that still carry the name column,
# fall back to the existing Hochschulen dim if a previous run already dropped
# 'Hochschule' from Studierende (this cell stays idempotent).
def _load_hochschule_names():
    for tbl in ("Studierende", "StudienanfaengerHochschule"):
        try:
            sdf = spark.table(f"{LAKEHOUSE_SCHEMA}.{tbl}")
            if {"Hochschule_Code", "Hochschule"}.issubset(set(sdf.columns)):
                print(f"Sourcing Hochschule names from {LAKEHOUSE_SCHEMA}.{tbl}")
                return (sdf.select("Hochschule_Code", "Hochschule")
                           .where("Hochschule_Code IS NOT NULL")
                           .distinct().toPandas()
                           .rename(columns={"Hochschule_Code": "EF1",
                                            "Hochschule": "Name_Genesis"}))
        except Exception as e:
            print(f"  skip {tbl}: {e}")
    print(f"Falling back to existing {LAKEHOUSE_SCHEMA}.Hochschulen")
    sdf = spark.table(f"{LAKEHOUSE_SCHEMA}.Hochschulen")
    return (sdf.select("Hochschule_Code", "Hochschule")
               .where("Hochschule_Code IS NOT NULL")
               .distinct().toPandas()
               .rename(columns={"Hochschule_Code": "EF1",
                                "Hochschule": "Name_Genesis"}))

base_pdf = _load_hochschule_names()
print(f"Distinct Hochschulen: {len(base_pdf)}")

# 2. Wikidata SPARQL — all higher-education institutions in Germany
sparql = """
SELECT ?item ?itemLabel ?coord ?bundeslandLabel ?inception WHERE {
  ?item wdt:P31/wdt:P279* wd:Q38723 .
  ?item wdt:P17 wd:Q183 .
  OPTIONAL { ?item wdt:P625 ?coord. }
  OPTIONAL { ?item wdt:P131 ?bundesland. ?bundesland wdt:P31 wd:Q1221156. }
  OPTIONAL { ?item wdt:P571 ?inception. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de,en". }
}
"""
resp = requests.get(
    "https://query.wikidata.org/sparql",
    params={"query": sparql, "format": "json"},
    headers={"User-Agent": "Hochschul-Insights/1.0 (alkorn@microsoft.com)"},
    timeout=120,
)
resp.raise_for_status()
rows = json.loads(resp.text, strict=False)["results"]["bindings"]
print(f"Wikidata returned {len(rows)} entities")


def _parse_coord(c):
    if not c:
        return None, None
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", c)
    return (float(m.group(2)), float(m.group(1))) if m else (None, None)


wd_records = []
for r in rows:
    qid = r["item"]["value"].rsplit("/", 1)[-1]
    name = r.get("itemLabel", {}).get("value")
    lat, lon = _parse_coord(r.get("coord", {}).get("value"))
    bl = r.get("bundeslandLabel", {}).get("value")
    inc = r.get("inception", {}).get("value", "")[:4] or None
    wd_records.append({"QID": qid, "Wiki_Name": name, "Lat": lat, "Lon": lon,
                       "Bundesland_Wiki": bl, "Gruendungsjahr": inc})
wd_df = pd.DataFrame(wd_records).drop_duplicates(subset=["QID"])
wd_by_qid = wd_df.set_index("QID").to_dict(orient="index")


# 3. Name normalization for fuzzy matching
def _norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(universitaet|universitat|university|hochschule|hs|fh|"
               r"fachhochschule|technische|technical|der|des|die|das|"
               r"stiftung|gmbh|e\.v\.|ev)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


wd_df["norm"] = wd_df["Wiki_Name"].map(_norm)
norm_to_qid = {n: q for n, q in zip(wd_df["norm"], wd_df["QID"]) if n}
all_norms = list(norm_to_qid.keys())


# 4. For each EF1, pick QID via Option C, else Option A
def _resolve(ef1, name):
    if ef1 in CURATED_EF1_TO_QID:
        qid = CURATED_EF1_TO_QID[ef1]
        if qid in wd_by_qid:
            return qid, "C"
    n = _norm(name)
    if n in norm_to_qid:
        return norm_to_qid[n], "A"
    hits = get_close_matches(n, all_norms, n=1, cutoff=0.92)
    if hits:
        return norm_to_qid[hits[0]], "A"
    return None, None


resolved = base_pdf.apply(lambda r: pd.Series(_resolve(r["EF1"], r["Name_Genesis"]),
                                              index=["QID", "Source"]), axis=1)
dim = pd.concat([base_pdf, resolved], axis=1)
dim = dim.merge(wd_df[["QID", "Wiki_Name", "Lat", "Lon", "Bundesland_Wiki", "Gruendungsjahr"]],
                on="QID", how="left")

# 4b. City lookup — Wikidata German cities >20k with Bundesland.
print("Fetching German cities from Wikidata for geocoding ...")
city_sparql = """
SELECT ?city ?cityLabel ?coord ?bundeslandLabel WHERE {
  ?city wdt:P31/wdt:P279* wd:Q515 .
  ?city wdt:P17 wd:Q183 .
  ?city wdt:P625 ?coord .
  OPTIONAL { ?city wdt:P131* ?bundesland . ?bundesland wdt:P31 wd:Q1221156 . }
  OPTIONAL { ?city wdt:P1082 ?pop. }
  FILTER(!BOUND(?pop) || ?pop > 20000)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
}
"""
cresp = requests.get("https://query.wikidata.org/sparql",
                     params={"query": city_sparql, "format": "json"},
                     headers={"User-Agent": "Hochschul-Insights/1.0 (alkorn@microsoft.com)"},
                     timeout=120)
cresp.raise_for_status()
city_rows = json.loads(cresp.text, strict=False)["results"]["bindings"]
city_lookup = {}   # normalized name -> (lat, lon, label, bundesland)
city_array  = []   # list of (lat, lon, label, bundesland) for nearest-neighbor
for cr in city_rows:
    label = cr.get("cityLabel", {}).get("value")
    lat, lon = _parse_coord(cr.get("coord", {}).get("value"))
    bl = cr.get("bundeslandLabel", {}).get("value")
    if not label or lat is None:
        continue
    key = _norm(label)
    if key and key not in city_lookup:
        city_lookup[key] = (lat, lon, label, bl)
    city_array.append((lat, lon, label, bl))
print(f"  loaded {len(city_lookup)} German cities ({len(city_array)} rows incl. duplicates)")

_NOISE = re.compile(
    r"\b(u|tu|th|fh|hs|uni|universitaet|universitat|university|hochschule|"
    r"fachhochschule|technische|technical|der|des|die|das|fuer|fur|und|of|in|"
    r"angewandte|wissenschaften|stiftung|gmbh|ev|kunst|musik|sport|medien|"
    r"katholische|evangelische|theologische|paedagogische|padagogische|"
    r"private|staatliche|kirchliche|kunsthochschule|musikhochschule|"
    r"verwaltungs|verwaltung|berufsakademie|akademie|institut)\b", re.I)


def _city_from_name(name):
    """Returns (lat, lon, label, bundesland) or (None, None, None, None)."""
    n = _norm(name)
    n = _NOISE.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    tokens = n.split()
    for size in (len(tokens), 3, 2, 1):
        if size <= 0 or size > len(tokens):
            continue
        for i in range(len(tokens) - size + 1):
            cand = " ".join(tokens[i:i + size])
            if cand in city_lookup:
                return city_lookup[cand]
    return None, None, None, None


def _nearest_city(lat, lon, max_km=30):
    """Reverse geocode lat/lon to nearest city. Returns (label, bundesland) or (None, None)."""
    best = (None, None)
    best_d2 = float("inf")
    cos_lat = 0.66  # cos(~50°) — Germany
    for clat, clon, clabel, cbl in city_array:
        dlat = (clat - lat) * 111.0
        dlon = (clon - lon) * 111.0 * cos_lat
        d2 = dlat * dlat + dlon * dlon
        if d2 < best_d2:
            best_d2 = d2
            best = (clabel, cbl)
    return best if best_d2 <= max_km * max_km else (None, None)


# 4c. Name-based city resolution — fills Stadt + (when missing) Lat/Lon/Bundesland.
dim["Stadt"] = None
for idx in dim.index:
    lat, lon, label, bl = _city_from_name(dim.at[idx, "Name_Genesis"])
    if label is None:
        continue
    dim.at[idx, "Stadt"] = label
    if pd.isna(dim.at[idx, "Lat"]):
        dim.at[idx, "Lat"] = lat
        dim.at[idx, "Lon"] = lon
        if dim.at[idx, "Source"] is None or pd.isna(dim.at[idx, "Source"]):
            dim.at[idx, "Source"] = "City"
    if not dim.at[idx, "Bundesland_Wiki"]:
        dim.at[idx, "Bundesland_Wiki"] = bl

# 4d. Reverse-geocode pass — rows with coords but still no Stadt -> nearest city.
need_city = dim["Stadt"].isna() & dim["Lat"].notna()
if need_city.any():
    print(f"Reverse-geocoding {int(need_city.sum())} Hochschulen with coords but no city ...")
    filled = 0
    for idx in dim.index[need_city]:
        label, bl = _nearest_city(dim.at[idx, "Lat"], dim.at[idx, "Lon"])
        if label:
            dim.at[idx, "Stadt"] = label
            if not dim.at[idx, "Bundesland_Wiki"]:
                dim.at[idx, "Bundesland_Wiki"] = bl
            filled += 1
    print(f"  -> {filled} resolved via nearest city (<=30 km)")

print(f"\nCoverage: Lat/Lon {dim['Lat'].notna().sum()}/{len(dim)}, "
      f"Stadt {dim['Stadt'].notna().sum()}/{len(dim)}, "
      f"Bundesland {dim['Bundesland_Wiki'].astype(bool).sum()}/{len(dim)}")
print("Source distribution:")
print(dim["Source"].fillna("none").value_counts())


# 4e. MANUAL overrides — force Stadt + Bundesland (and Lat/Lon when city known)
manual_hits = 0
for idx in dim.index:
    nm = dim.at[idx, "Name_Genesis"]
    if nm not in MANUAL_NAME_TO_CITY:
        continue
    city, bl = MANUAL_NAME_TO_CITY[nm]
    if city:
        dim.at[idx, "Stadt"] = city
        ck = _norm(city)
        if ck in city_lookup:
            clat, clon, _, cbl = city_lookup[ck]
            if pd.isna(dim.at[idx, "Lat"]):
                dim.at[idx, "Lat"], dim.at[idx, "Lon"] = clat, clon
                if dim.at[idx, "Source"] is None or pd.isna(dim.at[idx, "Source"]):
                    dim.at[idx, "Source"] = "Manual"
    if bl:
        dim.at[idx, "Bundesland_Wiki"] = bl
    manual_hits += 1
print(f"Manual mapping applied to {manual_hits} Hochschulen")


# 4f. Bundesland backfill — every row with a Stadt should also have a Bundesland.
# Cascade: (1) >20k city_lookup, (2) full Wikidata Gemeinde lookup (one extra
# SPARQL, cached), (3) MANUAL_NAME_TO_CITY-derived fallback, (4) curated
# city -> BL last-resort table for special cases.
_STADT_FALLBACK = {city: bl for (city, bl) in MANUAL_NAME_TO_CITY.values() if city and bl}
_CURATED_CITY_BL = {
    "Berlin": "Berlin", "Hamburg": "Hamburg", "München": "Bayern",
    "Köln": "Nordrhein-Westfalen", "Frankfurt am Main": "Hessen",
    "Stuttgart": "Baden-Württemberg", "Düsseldorf": "Nordrhein-Westfalen",
    "Leipzig": "Sachsen", "Dortmund": "Nordrhein-Westfalen",
    "Essen": "Nordrhein-Westfalen", "Bremen": "Bremen",
    "Dresden": "Sachsen", "Hannover": "Niedersachsen",
    "Nürnberg": "Bayern", "Duisburg": "Nordrhein-Westfalen",
    "Bochum": "Nordrhein-Westfalen", "Wuppertal": "Nordrhein-Westfalen",
    "Bielefeld": "Nordrhein-Westfalen", "Bonn": "Nordrhein-Westfalen",
    "Münster": "Nordrhein-Westfalen", "Karlsruhe": "Baden-Württemberg",
    "Mannheim": "Baden-Württemberg", "Augsburg": "Bayern",
    "Wiesbaden": "Hessen", "Gelsenkirchen": "Nordrhein-Westfalen",
    "Mönchengladbach": "Nordrhein-Westfalen", "Braunschweig": "Niedersachsen",
    "Chemnitz": "Sachsen", "Kiel": "Schleswig-Holstein",
    "Aachen": "Nordrhein-Westfalen", "Halle (Saale)": "Sachsen-Anhalt",
    "Magdeburg": "Sachsen-Anhalt", "Freiburg im Breisgau": "Baden-Württemberg",
    "Krefeld": "Nordrhein-Westfalen", "Lübeck": "Schleswig-Holstein",
    "Oberhausen": "Nordrhein-Westfalen", "Erfurt": "Thüringen",
    "Mainz": "Rheinland-Pfalz", "Rostock": "Mecklenburg-Vorpommern",
    "Kassel": "Hessen", "Hagen": "Nordrhein-Westfalen",
    "Saarbrücken": "Saarland", "Potsdam": "Brandenburg",
    "Oldenburg": "Niedersachsen", "Heidelberg": "Baden-Württemberg",
    "Darmstadt": "Hessen", "Paderborn": "Nordrhein-Westfalen",
    "Göttingen": "Niedersachsen", "Jena": "Thüringen",
    "Würzburg": "Bayern", "Regensburg": "Bayern",
    "Ingolstadt": "Bayern", "Ulm": "Baden-Württemberg",
    "Wolfsburg": "Niedersachsen", "Heilbronn": "Baden-Württemberg",
    "Ausland": "",
}


def _need_bl(idx):
    bl = dim.at[idx, "Bundesland_Wiki"]
    return (bl is None) or (isinstance(bl, float) and pd.isna(bl)) or (str(bl).strip() == "")


def _has_stadt(idx):
    s = dim.at[idx, "Stadt"]
    return isinstance(s, str) and s.strip() != ""


# Pass 1 — already-loaded >20k city lookup
filled1 = 0
for idx in dim.index:
    if not _has_stadt(idx) or not _need_bl(idx):
        continue
    s = dim.at[idx, "Stadt"]
    rec = city_lookup.get(_norm(s))
    if rec and rec[3]:
        dim.at[idx, "Bundesland_Wiki"] = rec[3]
        filled1 += 1
print(f"  BL pass 1 (>20k cities):       +{filled1}")

# Pass 2 — full Gemeinde lookup, only if anything still missing
need_pass2 = sum(1 for idx in dim.index if _has_stadt(idx) and _need_bl(idx))
filled2 = 0
if need_pass2:
    print(f"  Fetching all German Gemeinden from Wikidata for {need_pass2} pending rows ...")
    g_sparql = """
    SELECT ?g ?gLabel ?bundeslandLabel WHERE {
      ?g wdt:P31/wdt:P279* wd:Q262166 .
      ?g wdt:P131* ?bundesland .
      ?bundesland wdt:P31 wd:Q1221156 .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
    }
    """
    gresp = requests.get(
        "https://query.wikidata.org/sparql",
        params={"query": g_sparql, "format": "json"},
        headers={"User-Agent": "Hochschul-Insights/1.0 (alkorn@microsoft.com)"},
        timeout=180,
    )
    gresp.raise_for_status()
    g_lookup = {}  # normalized name -> Bundesland
    for r in json.loads(gresp.text, strict=False)["results"]["bindings"]:
        nm = r.get("gLabel", {}).get("value")
        bl = r.get("bundeslandLabel", {}).get("value")
        if not nm or not bl or bl.startswith("Q"):
            continue
        k = _norm(nm)
        if k and k not in g_lookup:
            g_lookup[k] = bl
    print(f"  loaded {len(g_lookup)} Gemeinden")
    for idx in dim.index:
        if not _has_stadt(idx) or not _need_bl(idx):
            continue
        s = dim.at[idx, "Stadt"]
        bl = g_lookup.get(_norm(s))
        if bl:
            dim.at[idx, "Bundesland_Wiki"] = bl
            filled2 += 1
    print(f"  BL pass 2 (all Gemeinden):     +{filled2}")

# Pass 3 — fallback derived from MANUAL_NAME_TO_CITY (city -> bl)
filled3 = 0
for idx in dim.index:
    if not _has_stadt(idx) or not _need_bl(idx):
        continue
    bl = _STADT_FALLBACK.get(dim.at[idx, "Stadt"])
    if bl:
        dim.at[idx, "Bundesland_Wiki"] = bl
        filled3 += 1
print(f"  BL pass 3 (manual map fallback): +{filled3}")

# Pass 4 — curated city -> BL table for major cities
filled4 = 0
for idx in dim.index:
    if not _has_stadt(idx) or not _need_bl(idx):
        continue
    bl = _CURATED_CITY_BL.get(dim.at[idx, "Stadt"])
    if bl is not None:
        dim.at[idx, "Bundesland_Wiki"] = bl
        filled4 += 1
print(f"  BL pass 4 (curated big cities):  +{filled4}")

# Residuals — print so they can be added to MANUAL_NAME_TO_CITY / _CURATED_CITY_BL
residuals = [(dim.at[i, "EF1"], dim.at[i, "Name_Genesis"], dim.at[i, "Stadt"])
             for i in dim.index if _has_stadt(i) and _need_bl(i)]
if residuals:
    print(f"\n  WARNING: {len(residuals)} rows still without Bundesland:")
    for ef1, nm, s in residuals[:25]:
        print(f"    {ef1}  {nm[:60]:60s}  Stadt='{s}'")


# 4g. Stadt <-> Bundesland CONFLICT resolution.
# When Stadt was correctly parsed from the GENESIS name but Wikidata QID was a
# fuzzy mis-match (e.g. HS6830 Reutlingen -> HTW Berlin), the row carries Berlin
# Bundesland + Berlin Lat/Lon. Detect the conflict and trust the city.
def _city_to_bl(city):
    if not city:
        return None
    ck = _norm(city)
    if ck in city_lookup:
        _clat, _clon, _cname, _cbl = city_lookup[ck]
        if _cbl:
            return _cbl
    if ck in _CURATED_CITY_BL:
        return _CURATED_CITY_BL[ck] or None
    if ck in _STADT_FALLBACK:
        return _STADT_FALLBACK[ck] or None
    return None

conflicts = 0
for idx in dim.index:
    stadt = dim.at[idx, "Stadt"]
    cur_bl = dim.at[idx, "Bundesland_Wiki"]
    if not stadt or not cur_bl:
        continue
    expected_bl = _city_to_bl(stadt)
    if expected_bl and expected_bl != cur_bl:
        dim.at[idx, "Bundesland_Wiki"] = expected_bl
        ck = _norm(stadt)
        if ck in city_lookup:
            clat, clon, _cn, _cbl = city_lookup[ck]
            if clat is not None and clon is not None:
                dim.at[idx, "Lat"] = clat
                dim.at[idx, "Lon"] = clon
        dim.at[idx, "Source"] = "City-corrected"
        conflicts += 1
print(f"  Step 4g: corrected {conflicts} Stadt<->Bundesland conflicts (fuzzy QID mismatches).")


# 4c. Parent University — collapse multi-campus private chains so the report
# can group all Fresenius / IU campuses under one parent. Match is a plain
# case-sensitive substring; for everything else Parent_University equals the
# Hochschule name itself.
PARENT_UNIVERSITY_RULES = [
    ("Fresenius", "Hochschule Fresenius"),
    ("IU Int.",   "IU Internationale Hochschule"),
]


def _parent_university(name):
    if not name:
        return name
    for needle, parent in PARENT_UNIVERSITY_RULES:
        if needle in name:
            return parent
    return name


dim["Parent_University"] = dim["Name_Genesis"].map(_parent_university)
print("\nParent University grouping:")
print(dim[dim["Parent_University"] != dim["Name_Genesis"]]
      .groupby("Parent_University").size().sort_values(ascending=False))

# 5a. Normalize Bundesland_Wiki -> GENESIS short form (so it joins Genesis.Bundesland
# and Power BI map geocoding picks it up). Wikidata returns e.g. "Freie Hansestadt Bremen".
_BL_NORMALIZE = {
    "Freie Hansestadt Bremen": "Bremen",
    "Freie und Hansestadt Hamburg": "Hamburg",
    "Land Berlin": "Berlin",
    "Freistaat Bayern": "Bayern",
    "Freistaat Sachsen": "Sachsen",
    "Freistaat Thüringen": "Thüringen",
}
dim["Bundesland_Wiki"] = (dim["Bundesland_Wiki"]
                          .replace(_BL_NORMALIZE)
                          .where(lambda s: s.astype(bool), other=None))
print("Bundesland_Wiki value counts after normalization:")
print(dim["Bundesland_Wiki"].fillna("<none>").value_counts())

# 5. Write Delta table
sdf = spark.createDataFrame(dim[["EF1", "Name_Genesis", "Parent_University",
                                 "QID", "Source",
                                 "Wiki_Name", "Lat", "Lon",
                                 "Bundesland_Wiki", "Gruendungsjahr",
                                 "Stadt"]]
                            .rename(columns={"EF1": "Hochschule_Code",
                                             "Name_Genesis": "Hochschule",
                                             "Bundesland_Wiki": "Bundesland"}))
(sdf.write
    .format("delta")
    .option("overwriteSchema", "true")
    .mode("overwrite")
    .saveAsTable(f"{LAKEHOUSE_SCHEMA}.Hochschulen"))
print(f"Wrote {sdf.count()} rows to {LAKEHOUSE_SCHEMA}.Hochschulen")
display(sdf.limit(10))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Attribute dimensions + skinny facts
# 
# Build small lookup dimensions (Bundesland, Hochschulart, Faechergruppe, Geschlecht, Nationalitaet) by union-DISTINCTing the matching column across every fact that contains it.
# 
# Then drop the Hochschule *name* column from Genesis.Studierende — it now lives only in Genesis.Hochschulen, joined via Hochschule_Code.

# CELL ********************

from pyspark.sql import functions as F
from functools import reduce

DIM_SOURCES = {
    "Bundesland": [
        ("Hochschulfinanzen", "Bundesland"),
        ("Ausgaben",          "Bundesland"),
        ("Einnahmen",         "Bundesland"),
        ("Drittmittel",       "Bundesland"),
    ],
    "Hochschulart": [
        ("Ausgaben",    "Hochschulart"),
        ("Einnahmen",   "Hochschulart"),
        ("Drittmittel", "Hochschulart"),
    ],
    "Faechergruppe": [
        ("Ausgaben",    "Faechergruppe"),
        ("Einnahmen",   "Faechergruppe"),
        ("Drittmittel", "Faechergruppe"),
        ("Professoren", "Faechergruppe"),
    ],
    "Geschlecht": [
        ("Hochschulpersonal",          "Geschlecht"),
        ("WissPersonalFach",           "Geschlecht"),
        ("Professoren",                "Geschlecht"),
        ("StudierendeBund",            "Geschlecht"),
        ("Studierende",                "Geschlecht"),
        ("StudienanfaengerHochschule", "Geschlecht"),
    ],
    "Nationalitaet": [
        ("StudierendeBund",            "Nationalitaet"),
        ("Studierende",                "Nationalitaet"),
        ("StudienanfaengerHochschule", "Nationalitaet"),
    ],
}

for dim_col, sources in DIM_SOURCES.items():
    parts = []
    for tbl, col in sources:
        try:
            parts.append(spark.table(f"{LAKEHOUSE_SCHEMA}.{tbl}").select(F.col(col).alias(dim_col)))
        except Exception as e:
            print(f"  skip {tbl}.{col}: {e}")
    if not parts:
        continue
    dim_sdf = (reduce(lambda a, b: a.unionByName(b), parts)
               .where(F.col(dim_col).isNotNull())
               .where(F.col(dim_col) != "")
               .distinct()
               .orderBy(dim_col))
    out = f"{LAKEHOUSE_SCHEMA}.{dim_col}"
    (dim_sdf.write
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .format("delta")
        .saveAsTable(out))
    print(f"  -> {out}: {dim_sdf.count()} distinct values")

# Inject Bundesland into Studierende fact from Hochschulen dimension, then drop Hochschule name.
print("\n► Injecting Bundesland into Studierende...")
studi = spark.table(f"{LAKEHOUSE_SCHEMA}.Studierende")
hochsch = spark.table(f"{LAKEHOUSE_SCHEMA}.Hochschulen").select("Hochschule_Code", "Bundesland")

# Join to get Bundesland
studi_with_bl = studi.join(hochsch, on="Hochschule_Code", how="left")

# Drop Hochschule name column (lives in dimension), keep Bundesland
cols_to_keep = [c for c in studi_with_bl.columns if c != "Hochschule"]
studi_final = studi_with_bl.select(*cols_to_keep)

(studi_final.write
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .format("delta")
    .saveAsTable(f"{LAKEHOUSE_SCHEMA}.Studierende"))

print(f"  ✓ Added 'Bundesland' to {LAKEHOUSE_SCHEMA}.Studierende")
print(f"  ✓ Dropped 'Hochschule' name (now in dimension)")
print(f"  Final columns: {studi_final.columns}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

