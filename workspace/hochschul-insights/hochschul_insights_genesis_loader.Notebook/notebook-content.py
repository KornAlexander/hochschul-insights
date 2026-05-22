# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "e012a50f-cbcc-45d2-8628-a20162f3a46e",
# META       "default_lakehouse_name": "DemoLakehouse",
# META       "default_lakehouse_workspace_id": "00000000-0000-0000-0000-000000000000",
# META       "known_lakehouses": [
# META         {
# META           "id": "e012a50f-cbcc-45d2-8628-a20162f3a46e"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Hochschul-Insights — GENESIS Loader
# 
# End-to-end loader for the **Hochschul-Insights** webinar demo. Pulls ten tables from the **DESTATIS GENESIS-Online REST API 2020** plus a Wikidata-enriched Hochschule dimension and five attribute dimensions, and lands them as Delta tables in the attached Lakehouse so a Direct Lake semantic model can sit on top.
# 
# ## Pipeline
# 
# ```
# DESTATIS GENESIS (ffcsv ZIP)
#         │
#         ▼
#   requests.post  ──►  zipfile.extract  ──►  pandas.read_csv (de-DE)
#         │
#         ▼
#   Spark DataFrame  ──►  Lakehouse Delta table (overwrite)
# 
# Wikidata SPARQL  ──►  Hochschule dim (EF1 + lat/lon, City fallback)
# DISTINCT facts  ──►  attribute dims (Bundesland, Hochschulart, …)
# ```
# 
# ## Tables landed (schema `Genesis`)
# 
# ### Facts
# 
# | Lakehouse table                       | GENESIS Code  | Grain                                                                      |
# |---------------------------------------|---------------|----------------------------------------------------------------------------|
# | `Genesis.Hochschulfinanzen`           | `21371-0010`  | Jahr × Bundesland × Kennzahl (Einnahmen / Ausgaben Total)                  |
# | `Genesis.Ausgaben`                    | `21371-0011`  | Jahr × Bundesland × Hochschulart × Fächergruppe                            |
# | `Genesis.Einnahmen`                   | `21371-0012`  | Jahr × Bundesland × Hochschulart × Fächergruppe (ohne Trägermittel)        |
# | `Genesis.Drittmittel`                 | `21371-0013`  | Jahr × Bundesland × Hochschulart × Fächergruppe                            |
# | `Genesis.Hochschulpersonal`           | `21341-0001`  | Jahr × Beschäftigungsverh. × Geschlecht (Bund)                             |
# | `Genesis.WissPersonalFach`            | `21341-0002`  | Jahr × Lehr-/Forschungsbereich × Geschlecht (Bund)                         |
# | `Genesis.Professoren`                 | `21341-0003`  | Jahr × Fächergruppe × Geschlecht (Bund)                                    |
# | `Genesis.StudierendeBund`             | `21311-0001`  | WS × Nationalität × Geschlecht (Bundestrend, klein & schnell)              |
# | `Genesis.Studierende`                 | `21311-0002`  | WS × Hochschule_Code × Nationalität × Geschlecht                           |
# | `Genesis.StudienanfaengerHochschule`  | `21311-0011`  | WS × Hochschule_Code × Nationalität × Geschlecht                           |
# 
# ### Dimensions
# 
# | Lakehouse table              | Built from                              | Notes                                                  |
# |------------------------------|-----------------------------------------|--------------------------------------------------------|
# | `Genesis.Hochschulen`        | `Studierende` + Wikidata + city fallback| `Hochschule_Code` (EF1), Name, QID, Lat/Lon, Bundesland|
# | `Genesis.Bundesland`         | DISTINCT across BL-facts                | joins on column `Bundesland`                           |
# | `Genesis.Hochschulart`       | DISTINCT across Ausgaben/Einnahmen/Drittmittel | joins on column `Hochschulart`                  |
# | `Genesis.Faechergruppe`      | DISTINCT across Finanzen + Professoren  | joins on column `Faechergruppe`                        |
# | `Genesis.Geschlecht`         | DISTINCT across all Personen-Facts      | joins on column `Geschlecht`                           |
# | `Genesis.Nationalitaet`      | DISTINCT across Studierende-Facts       | joins on column `Nationalitaet`                        |
# 
# ## Prerequisites
# 
# 1. **GENESIS API token** — create one at https://www-genesis.destatis.de → Profile → API-Token. Paste into the config cell.
# 2. **Lakehouse attached** to this notebook — must be **schema-enabled**. For the webinar setup: Demo workspace Lakehouse attached as default, this notebook lives in the Webinar workspace.
# 3. Notebook runs on a **Fabric Spark pool** — `requests`, `pandas`, `pyspark` are pre-installed.
# 
# ## Operate
# 
# 1. Set `GENESIS_TOKEN` in the config cell.
# 2. Run All. The tables are overwritten on every run, so the report always reflects the latest GENESIS state.
# 3. Schedule the notebook (e.g. monthly — GENESIS data does not change that often).


# MARKDOWN ********************

# ## 1. Configuration
# 
# Token is passed in via `00_start_here` (parameter cell below). When run directly,
# paste your token into the parameters cell. Year ranges follow the webinar scope.


# PARAMETERS CELL ********************

GENESIS_TOKEN = ""  # https://www-genesis.destatis.de → Profile → API-Token


# CELL ********************

if not GENESIS_TOKEN.strip():
    raise ValueError("GENESIS_TOKEN not set — open 00_start_here and paste your token, or set the parameter.")

# ---- EDIT ME --------------------------------------------------------------
LAKEHOUSE_SCHEMA = "Genesis"                            # schema-enabled Lakehouse: tables land under this schema
# ---------------------------------------------------------------------------

TABLES = [
    # (genesis_code, start, end, lakehouse_table_name)
    ("21371-0010", "2019", "2022", "Hochschulfinanzen"),
    ("21371-0011", "2019", "2022", "Ausgaben"),                  # × BL × Hochschulart × Faechergruppe
    ("21371-0012", "2019", "2022", "Einnahmen"),                 # × BL × Hochschulart × Faechergruppe
    ("21371-0013", "2019", "2022", "Drittmittel"),               # × BL × Hochschulart × Faechergruppe
    ("21341-0001", "2019", "2023", "Hochschulpersonal"),
    ("21341-0002", "2019", "2023", "WissPersonalFach"),          # × Fach (Bund)
    ("21341-0003", "2019", "2023", "Professoren"),               # × Fach (Bund)
    ("21311-0001", "2019", "2024", "StudierendeBund"),           # Bund × Nationalität × Geschlecht
    ("21311-0002", "2019", "2024", "Studierende"),               # × Hochschule (PER_YEAR)
    ("21311-0011", "2019", "2024", "StudienanfaengerHochschule"),# × Hochschule (PER_YEAR)
]

BASE       = "https://www-genesis.destatis.de/genesisWS/rest/2020"
TABLE_URL  = f"{BASE}/data/tablefile"
RESULT_URL = f"{BASE}/data/resultfile"
JOBS_URL   = f"{BASE}/catalogue/jobs"
HEADERS    = {"username": GENESIS_TOKEN}

# Ensure target schema exists (Lakehouse must be schema-enabled).
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {LAKEHOUSE_SCHEMA}")
print(f"Will load {len(TABLES)} tables into schema '{LAKEHOUSE_SCHEMA}'.")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1b. Parameters	ables_to_load is overridden by the Fabric pipeline so each Notebook activity loads exactly one fact table. Empty list means *load everything* (interactive default).

# PARAMETERS CELL ********************

# ---- PIPELINE PARAMETER --------------------------------------------------
# Override from a Fabric Data Pipeline Notebook activity 'Base parameters'.
# Empty string => load all tables (default for interactive runs).
# Multi-table runs: pass a comma-separated string like 'Studierende,Professoren'.
tables_to_load = ""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. GENESIS fetcher
# 
# `fetch_ffcsv()` POSTs to `/data/tablefile`, unwraps the ZIP, returns a pandas DataFrame. For tables that exceed the synchronous size limit (`"Code":98`) it transparently falls back to the **async `job=true`** pattern (submit → poll `/catalogue/jobs` → download via `/data/resultfile`).
# 
# The `value` column is parsed with `de-DE` semantics: `-`, `.`, `...`, `/`, `x` become `null`.


# CELL ********************

import io
import re
import time
import zipfile
import requests
import pandas as pd

NULL_TOKENS = {"-", ".", "...", "/", "x", ""}


def _unzip_csv(content: bytes) -> pd.DataFrame:
    """Unwrap a GENESIS ZIP response and parse the inner CSV (semicolon, UTF-8)."""
    if content[:2] != b"PK":
        raise RuntimeError(f"Expected ZIP, got: {content[:300].decode('utf-8', errors='replace')}")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        inner = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
        if inner is None:
            raise RuntimeError("ZIP contained no CSV")
        with zf.open(inner) as fh:
            return pd.read_csv(fh, sep=";", encoding="utf-8", dtype=str, keep_default_na=False)


def _post(url: str, body: dict, *, json_mode: bool = False, timeout: int = 180):
    r = requests.post(url, headers=HEADERS, data=body, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} from {url}\nbody: {r.text[:800]}")
    return r.json() if json_mode else r.content


def fetch_ffcsv(name: str, start: str, end: str, *, filter1: tuple | None = None) -> pd.DataFrame:
    """Fetch a GENESIS table as a tidy DataFrame. Handles async job fallback.

    filter1 = (variable, key) restricts the first classifier server-side
    (e.g. ("DLAND", "DG01") for Schleswig-Holstein). Lets us bypass the sync
    size limit without needing a Premium token.
    """
    body = {
        "name": name, "area": "all", "compress": "false", "transpose": "false",
        "startyear": start, "endyear": end, "timeslices": "",
        "format": "ffcsv", "job": "false", "language": "de",
    }
    if filter1:
        body["classifyingvariable1"] = filter1[0]
        body["classifyingkey1"] = filter1[1]
    label = f"{name} {start}-{end}" + (f" [{filter1[0]}={filter1[1]}]" if filter1 else "")
    print(f"  POST {label}")
    content = _post(TABLE_URL, body)

    # Sync error? Check for "too big" → switch to async.
    if content[:2] != b"PK":
        err = content.decode("utf-8", errors="replace")
        if '"Code":98' in err or "job=true" in err:
            print("    Table too big → switching to async (job=true)")
            return _fetch_async(name, start, end)
        raise RuntimeError(f"GENESIS error: {err[:500]}")
    return _unzip_csv(content)


def _fetch_async(name: str, start: str, end: str) -> pd.DataFrame:
    body = {
        "name": name, "area": "all", "compress": "false", "transpose": "false",
        "startyear": start, "endyear": end, "timeslices": "",
        "format": "ffcsv", "job": "true", "language": "de",
    }
    js = _post(TABLE_URL, body, json_mode=True)
    status = (js.get("Status") or {}).get("Content", "")
    m = re.search(r"([0-9]+-[0-9]+_[0-9]+)", status)
    if not m:
        raise RuntimeError(f"Cannot parse job name from: {status}")
    job_name = m.group(1)
    print(f"    job submitted: {job_name}")

    for i in range(1, 41):
        time.sleep(5)
        jr = _post(JOBS_URL, {
            "selection": job_name, "searchcriterion": "Code", "sortcriterion": "Code",
            "type": "all", "pagelength": "10", "language": "de",
        }, json_mode=True)
        match = next((x for x in (jr.get("List") or []) if x.get("Code") == job_name), None)
        state = (match or {}).get("State", "<pending>")
        print(f"      poll {i}: {state}")
        if any(s in state for s in ("Fertig", "finished", "abgeschlossen")):
            break
    else:
        raise TimeoutError("Job did not finish within 200 seconds")

    content = _post(RESULT_URL, {
        "name": job_name, "area": "all", "compress": "false",
        "format": "ffcsv", "language": "de",
    })
    return _unzip_csv(content)


def parse_value(v: str):
    """Convert ffcsv value text → float (de-DE) or None."""
    if v is None:
        return None
    s = str(v).strip()
    if s in NULL_TOKENS:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except ValueError:
        return None


def parse_year(t: str):
    """Extract year (int) from `time` column. Works for '2021' and '2022-10P6M'."""
    if not t:
        return None
    try:
        return int(str(t)[:4])
    except ValueError:
        return None


print("Helpers ready.")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Per-table shaping
# 
# Each GENESIS table has its own classification dimensions. The shapers below project the raw ffcsv long-format into business-friendly column names (`Jahr`, `Bundesland`, `Kennzahl`, …) and convert `Wert` to numeric. They all return a pandas DataFrame ready for Spark.


# CELL ********************

def shape_common(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    year = df["time"].map(parse_year)
    # Jahr as actual date (1st of January) so Power BI / DAX time intelligence works.
    df["Jahr"] = pd.to_datetime(year.map(
        lambda y: f"{int(y)}-01-01" if pd.notna(y) else None
    ), errors="coerce")
    df["Wert"] = df["value"].map(parse_value)
    return df


SUBTOTAL_LABELS = {"Insgesamt", "Hochschule insgesamt"}


def _drop_subtotals(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Remove DESTATIS subtotal rows so SUM in DAX matches without double-counting."""
    mask = pd.Series(True, index=df.index)
    for c in cols:
        if c in df.columns:
            mask &= ~df[c].isin(SUBTOTAL_LABELS)
    return df[mask]


def shape_hochschulfinanzen(df: pd.DataFrame) -> pd.DataFrame:
    df = shape_common(df).rename(columns={
        "1_variable_attribute_label": "Bundesland",
        "value_variable_label":        "Kennzahl",
        "value_unit":                  "Einheit",
    })
    df["Wert_EUR"] = df["Wert"].map(lambda v: v * 1000 if v is not None else None)
    return df[["Jahr","Bundesland","Kennzahl","Wert_EUR"]]


def shape_drittmittel(df: pd.DataFrame) -> pd.DataFrame:
    """21351-0001/2/3: Ausgaben/Einnahmen/Drittmittel × Bundesland × Hochschulart × Fächergruppe.
    Kennzahl is constant within each table (label of the single value variable) and dropped."""
    df = shape_common(df).rename(columns={
        "1_variable_attribute_label": "Bundesland",
        "2_variable_attribute_label": "Hochschulart",
        "3_variable_attribute_label": "Faechergruppe",
    })
    df = _drop_subtotals(df, ["Hochschulart", "Faechergruppe"])
    df["Wert_EUR"] = df["Wert"].map(lambda v: v * 1000 if v is not None else None)
    return df[["Jahr","Bundesland","Hochschulart","Faechergruppe","Wert_EUR"]]


def shape_hochschulpersonal(df: pd.DataFrame) -> pd.DataFrame:
    df = shape_common(df).rename(columns={
        "2_variable_attribute_label": "Beschaeftigungsverhaeltnis",
        "3_variable_attribute_label": "Geschlecht",
    })
    df = _drop_subtotals(df, ["Beschaeftigungsverhaeltnis", "Geschlecht"])
    return df[["Jahr","Beschaeftigungsverhaeltnis","Geschlecht","Wert"]]


def shape_wiss_personal_fach(df: pd.DataFrame) -> pd.DataFrame:
    """21341-0002: hauptberufl. wiss. Personal × Lehr-/Forschungsbereich × Geschlecht (Bund)."""
    df = shape_common(df).rename(columns={
        "2_variable_attribute_label": "LehrForschungsbereich",
        "3_variable_attribute_label": "Geschlecht",
    })
    df = _drop_subtotals(df, ["LehrForschungsbereich", "Geschlecht"])
    return df[["Jahr","LehrForschungsbereich","Geschlecht","Wert"]]


def shape_professoren(df: pd.DataFrame) -> pd.DataFrame:
    """21341-0003: Professoren × Fächergruppe × Geschlecht (Bund)."""
    df = shape_common(df).rename(columns={
        "2_variable_attribute_label": "Faechergruppe",
        "3_variable_attribute_label": "Geschlecht",
    })
    df = _drop_subtotals(df, ["Faechergruppe", "Geschlecht"])
    return df[["Jahr","Faechergruppe","Geschlecht","Wert"]]


def _wintersemester(jahr_dt):
    if pd.isna(jahr_dt):
        return None
    y = jahr_dt.year
    return f"WS {y}/{str(y + 1)[-2:]}"


def shape_studierende(df: pd.DataFrame) -> pd.DataFrame:
    df = shape_common(df).rename(columns={
        "2_variable_attribute_label": "Nationalitaet",
        "3_variable_attribute_label": "Geschlecht",
        "4_variable_attribute_label": "Hochschule",
        "4_variable_attribute_code":  "Hochschule_Code",
    })
    # Drop subtotal rows so SUM in DAX matches DESTATIS Insgesamt without double-counting.
    df = df[(df["Geschlecht"] != "Insgesamt") & (df["Nationalitaet"] != "Insgesamt")]
    df["Wintersemester"] = df["Jahr"].map(_wintersemester)
    # Hochschule (Name) kept here so the Hochschule dimension cell can derive
    # the dim from this fact. After the dim is built, remove it via the
    # post-processing cell below to keep facts skinny.
    return df[["Jahr","Wintersemester","Hochschule","Hochschule_Code","Nationalitaet","Geschlecht","Wert"]]


def shape_studierende_bund(df: pd.DataFrame) -> pd.DataFrame:
    """21311-0001: Studierende Bund × Nationalität × Geschlecht. Gebiet is constant ("Deutschland") and dropped."""
    df = shape_common(df).rename(columns={
        "2_variable_attribute_label": "Nationalitaet",
        "3_variable_attribute_label": "Geschlecht",
    })
    df = df[(df["Geschlecht"] != "Insgesamt") & (df["Nationalitaet"] != "Insgesamt")]
    df["Wintersemester"] = df["Jahr"].map(_wintersemester)
    return df[["Jahr","Wintersemester","Nationalitaet","Geschlecht","Wert"]]


def shape_studienanfaenger_hochschule(df: pd.DataFrame) -> pd.DataFrame:
    """21311-0011: Studienanfänger × Hochschule × Nationalität × Geschlecht (Bund)."""
    df = shape_common(df).rename(columns={
        "2_variable_attribute_label": "Nationalitaet",
        "3_variable_attribute_label": "Geschlecht",
        "4_variable_attribute_label": "Hochschule",
        "4_variable_attribute_code":  "Hochschule_Code",
    })
    df["Wintersemester"] = df["Jahr"].map(_wintersemester)
    return df[["Jahr","Wintersemester","Hochschule_Code","Nationalitaet","Geschlecht","Wert"]]


SHAPERS = {
    "Hochschulfinanzen":          shape_hochschulfinanzen,
    "Ausgaben":                   shape_drittmittel,
    "Einnahmen":                  shape_drittmittel,
    "Drittmittel":                shape_drittmittel,
    "Hochschulpersonal":          shape_hochschulpersonal,
    "WissPersonalFach":           shape_wiss_personal_fach,
    "Professoren":                shape_professoren,
    "StudierendeBund":            shape_studierende_bund,
    "Studierende":                shape_studierende,
    "StudienanfaengerHochschule": shape_studienanfaenger_hochschule,
}
print("Shapers ready.")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Run the pipeline
# 
# Iterates through `TABLES`, fetches → shapes → writes to Lakehouse Delta with `mode="overwrite"`. The schema is allowed to evolve (`mergeSchema`) so a future column addition by DESTATIS won't break the run.


# CELL ********************

summary = []

from pyspark.sql import functions as F
from pyspark.sql.types import TimestampType

# Tables that are too large for sync but don't have Bundesland partitioning.
# Fetched year-by-year and concatenated (slower but reliable with free token).
PER_YEAR = {"21311-0002", "21311-0011"}  # Studierende/Studienanfänger × Hochschule

# Tables that exceed the sync size limit AND fail on async (free token has no
# Premium job=true). Fetched per Bundesland per year via server-side filter
# (classifyingvariable1=DLAND, classifyingkey1=DGxx) and concatenated.
PER_BL_PER_YEAR = set()  # disabled — free GENESIS token can't fetch these even per-BL
BL_KEYS = [f"DG{n:02d}" for n in range(1, 17)]  # DG01..DG16


def fetch_smart(genesis_code, start, end):
    # Year-by-year for tables that are too big for sync but have no BL partition
    if genesis_code in PER_YEAR:
        parts = []
        for y in range(int(start), int(end) + 1):
            print(f"    Fetching year {y}...")
            last_err = None
            for attempt in range(5):
                try:
                    parts.append(fetch_ffcsv(genesis_code, str(y), str(y)))
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    wait = 10 * (attempt + 1)
                    print(f"      attempt {attempt+1}/5 failed ({type(e).__name__}): retrying in {wait}s")
                    time.sleep(wait)
            if last_err is not None:
                raise last_err
        return pd.concat(parts, ignore_index=True)
    # Per-Bundesland per-year for regional tables (currently disabled)
    if genesis_code in PER_BL_PER_YEAR:
        parts = []
        for y in range(int(start), int(end) + 1):
            for bl in BL_KEYS:
                parts.append(fetch_ffcsv(genesis_code, str(y), str(y),
                                         filter1=("DLAND", bl)))
        return pd.concat(parts, ignore_index=True)
    last_err = None
    for attempt in range(5):
        try:
            return fetch_ffcsv(genesis_code, start, end)
        except Exception as e:
            last_err = e
            wait = 10 * (attempt + 1)
            print(f"    attempt {attempt+1}/5 failed ({type(e).__name__}): retrying in {wait}s")
            time.sleep(wait)
    raise last_err


# Parse tables_to_load (string from pipeline params, comma-separated). Empty = all.
_to_load = [s.strip() for s in (tables_to_load or "").split(",") if s.strip()]
_selected = [t for t in TABLES if (not _to_load) or t[3] in _to_load]
if _to_load:
    _missing = set(_to_load) - {t[3] for t in TABLES}
    if _missing:
        raise ValueError(f"Unknown table name(s) in tables_to_load: {_missing}")
print(f"Loading {len(_selected)} of {len(TABLES)} table(s): {[t[3] for t in _selected]}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Main fetch -> shape -> save loop. Idempotent: overwrites Delta tables each run.
for code, start, end, name in _selected:
    print(f"\n=== {name} ({code}) {start}-{end} ===")
    raw = fetch_smart(code, start, end)
    print(f"  fetched {len(raw)} raw rows")
    shaped = SHAPERS[name](raw)
    print(f"  shaped {len(shaped)} rows -> columns: {list(shaped.columns)}")
    sdf = spark.createDataFrame(shaped)
    target = f"{LAKEHOUSE_SCHEMA}.{name}"
    (sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target))
    n = spark.table(target).count()
    summary.append({"table": name, "rows": n})
    print(f"  wrote {n} rows -> {target}")

print("\n=== Summary ===")
print(pd.DataFrame(summary))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. Sanity check
# 
# Quick preview of each table so we can verify the shaping was correct before consuming it from the semantic model.


# CELL ********************

_to_load = [s.strip() for s in (tables_to_load or "").split(",") if s.strip()]
_selected = [t for t in TABLES if (not _to_load) or t[3] in _to_load]
for _, _, _, name in _selected:
    table_name = f"{LAKEHOUSE_SCHEMA}.{name}"
    print(f"\n=== {table_name} ===")
    display(spark.table(table_name).limit(5))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

