# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "e012a50f-cbcc-45d2-8628-a20162f3a46e",
# META       "default_lakehouse_name": "hochschul_insights_lh",
# META       "default_lakehouse_workspace_id": "__WORKSPACE_ID__",
# META       "known_lakehouses": [
# META         {
# META           "id": "e012a50f-cbcc-45d2-8628-a20162f3a46e"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# ## Hochschul-Insights — Start Here
# 
# This is the **single entry point** for the Hochschul-Insights solution. It orchestrates
# the other notebooks in this workspace so you only ever need to run *this one*.
# 
# ### What this notebook does
# 
# When you **Run All**, it picks one of two modes based on whether you supply a GENESIS
# token, then calls the matching child notebook(s) to populate the `Genesis` schema in
# the **`hochschul_insights_lh`** Lakehouse. The **HochschulInsights** report reads
# directly from that Lakehouse (Direct Lake), so once the load finishes the report is live.
# 
# | Mode | Trigger | What runs | Source | Time |
# |------|---------|-----------|--------|------|
# | **Snapshot** *(default)* | `GENESIS_TOKEN` is empty | `hochschul_insights_load_snapshot` | Bundled CSVs in `/Files/snapshot/` | ~1 min |
# | **Live** | `GENESIS_TOKEN` is set | `hochschul_insights_genesis_loader` → `hochschul_insights_genesis_dimensions` | DESTATIS GENESIS API + Wikidata | ~10–15 min |
# 
# ### How to use it
# 
# 1. **Snapshot (no setup):** leave the token empty in the cell below and **Run All**.
#    Loads the bundled CSV snapshot into Delta tables — perfect for a first look or a demo.
# 2. **Live refresh:** register a **free** account at
#    https://www-genesis.destatis.de/ → *Profile → API-Token*, paste the token into
#    `GENESIS_TOKEN` below, and **Run All**. Pulls fresh figures from the DESTATIS API
#    and enriches universities with geo/metadata from Wikidata.
# 
# ### Prerequisites
# 
# - The **`hochschul_insights_lh`** Lakehouse must be attached as this notebook's
#   **default** Lakehouse (it is, if you deployed via the jumpstart installer). The child
#   notebooks inherit it via `useRootDefaultLakehouse=True`, so the attachment only needs
#   to exist here.
# 
# When the run finishes, open the **HochschulInsights** report in this workspace.

# CELL ********************

# === Configuration ===
# Paste your free DESTATIS GENESIS token here to pull live data.
# Leave it empty ("") to load the bundled snapshot instead (default, no setup needed).
GENESIS_TOKEN = ""

import notebookutils as nu

if GENESIS_TOKEN.strip():
    # Live mode: fetch fresh figures from DESTATIS, then build dimension tables.
    print("Token provided -> running live GENESIS load (10-15 min)")
    nu.notebook.run("hochschul_insights_genesis_loader",
                    arguments={"GENESIS_TOKEN": GENESIS_TOKEN, "useRootDefaultLakehouse": True})
    nu.notebook.run("hochschul_insights_genesis_dimensions",
                    arguments={"useRootDefaultLakehouse": True})
else:
    # Snapshot mode: load the bundled CSVs shipped in the Lakehouse Files area.
    print("No token -> loading bundled snapshot from /Files/snapshot/")
    nu.notebook.run("hochschul_insights_load_snapshot",
                    arguments={"useRootDefaultLakehouse": True})

print("\nDone. Open the HochschulInsights report in this workspace.")

