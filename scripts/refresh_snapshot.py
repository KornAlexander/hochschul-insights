"""
refresh_snapshot.py — regenerate data/snapshot/*.csv from a freshly loaded Lakehouse.

Run this from a Fabric notebook attached to the `hochschul_insights_lh` Lakehouse
AFTER running the live-mode loader + dimensions notebooks. It exports every Delta
table under schema `Genesis` back to CSV with a stable column order so the
snapshot CSVs match the DataFrames produced by the live loader exactly.

Usage (in a Fabric notebook cell):
    %run scripts/refresh_snapshot.py
    # then download /lakehouse/default/Files/snapshot_export/ via the Lakehouse UI
    # and commit them to data/snapshot/ in the repo.
"""

import os
from pyspark.sql import SparkSession

OUT = "/lakehouse/default/Files/snapshot_export"
os.makedirs(OUT, exist_ok=True)

spark = SparkSession.builder.getOrCreate()

# Tables in dependency order (matches data/manifest.json)
TABLES = [
    "Ausgaben", "Einnahmen", "Drittmittel", "Hochschulfinanzen",
    "Hochschulpersonal", "WissPersonalFach", "Professoren",
    "StudierendeBund", "Studierende", "StudienanfaengerHochschule",
    "Hochschulen",
    "Bundesland", "Hochschulart", "Faechergruppe", "Geschlecht", "Nationalitaet",
]

for t in TABLES:
    df = spark.table(f"Genesis.{t.lower()}")
    pdf = df.toPandas()
    out = f"{OUT}/{t}.csv"
    pdf.to_csv(out, index=False)
    print(f"OK {t}: {len(pdf):,} rows -> {out}")

print(f"\nDone. Download from {OUT} and commit to data/snapshot/.")
