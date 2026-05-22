# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "e012a50f-cbcc-45d2-8628-a20162f3a46e",
# META       "default_lakehouse_name": "WebinarLakehouse",
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

# # Hochschul-Insights — Snapshot Loader
#
# Offline / no-token alternative to the GENESIS Loader.
# Reads CSV snapshots from the Lakehouse `/Files/snapshot/` folder
# (auto-uploaded by the Jumpstart deploy from `data/snapshot/`)
# and writes them as Delta tables to schema `Genesis` with explicit
# schemas that match the Direct Lake semantic model exactly
# (Jahr → TimestampType, numeric Wert columns → DoubleType, etc.).

# CELL ********************

import os, io, pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType
)

spark = SparkSession.builder.getOrCreate()
spark.sql("CREATE SCHEMA IF NOT EXISTS Genesis")

SNAP_DIR = "/lakehouse/default/Files/snapshot"

# Per-table schemas (must mirror semantic model column types)
S = StringType
D = DoubleType
T = TimestampType

SCHEMAS = {
    "Ausgaben":                 [("Jahr",T()),("Bundesland",S()),("Hochschulart",S()),("Faechergruppe",S()),("Wert_EUR",D())],
    "Einnahmen":                [("Jahr",T()),("Bundesland",S()),("Hochschulart",S()),("Faechergruppe",S()),("Wert_EUR",D())],
    "Drittmittel":              [("Jahr",T()),("Bundesland",S()),("Hochschulart",S()),("Faechergruppe",S()),("Wert_EUR",D())],
    "Hochschulfinanzen":        [("Jahr",T()),("Bundesland",S()),("Kennzahl",S()),("Wert_EUR",D())],
    "Hochschulpersonal":        [("Jahr",T()),("Beschaeftigungsverhaeltnis",S()),("Geschlecht",S()),("Wert",D())],
    "WissPersonalFach":         [("Jahr",T()),("LehrForschungsbereich",S()),("Geschlecht",S()),("Wert",D())],
    "Professoren":              [("Jahr",T()),("Faechergruppe",S()),("Geschlecht",S()),("Wert",D())],
    "StudierendeBund":          [("Jahr",T()),("Wintersemester",S()),("Nationalitaet",S()),("Geschlecht",S()),("Wert",D())],
    "Studierende":              [("Hochschule_Code",S()),("Jahr",T()),("Wintersemester",S()),("Nationalitaet",S()),("Geschlecht",S()),("Wert",D()),("Bundesland",S())],
    "StudienanfaengerHochschule":[("Jahr",T()),("Wintersemester",S()),("Hochschule_Code",S()),("Nationalitaet",S()),("Geschlecht",S()),("Wert",D())],
    "Hochschulen":              [("Hochschule_Code",S()),("Hochschule",S()),("Parent_University",S()),("QID",S()),("Source",S()),("Wiki_Name",S()),("Lat",D()),("Lon",D()),("Bundesland",S()),("Gruendungsjahr",S()),("Stadt",S())],
    "Bundesland":               [("Bundesland",S())],
    "Hochschulart":             [("Hochschulart",S())],
    "Faechergruppe":            [("Faechergruppe",S())],
    "Geschlecht":               [("Geschlecht",S())],
    "Nationalitaet":            [("Nationalitaet",S())],
}

def build_schema(cols):
    return StructType([StructField(n, t, True) for n, t in cols])

def load(table, cols):
    path = f"{SNAP_DIR}/{table}.csv"
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    # Parse dates for Jahr; keep everything else as string in pandas, cast to schema in Spark
    parse_dates = [n for n, t in cols if isinstance(t, TimestampType)]
    dtype_map = {n: ("float64" if isinstance(t, DoubleType) else "object")
                 for n, t in cols if not isinstance(t, TimestampType)}
    pdf = pd.read_csv(path, parse_dates=parse_dates, dtype=dtype_map)
    # Force NaN string cells to actual None for Spark
    for n, t in cols:
        if isinstance(t, StringType):
            pdf[n] = pdf[n].where(pdf[n].notna(), None)
    sdf = spark.createDataFrame(pdf, schema=build_schema(cols))
    target = f"Genesis.{table.lower()}"
    (sdf.write.format("delta").mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(target))
    return target, sdf.count()

for table, cols in SCHEMAS.items():
    try:
        name, n = load(table, cols)
        print(f"OK {name}: {n:,} rows")
    except Exception as e:
        print(f"FAIL {table}: {e}")

print("Snapshot load done.")

