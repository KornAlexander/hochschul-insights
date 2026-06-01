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
# Welcome! This notebook routes between **snapshot mode** (no setup) and **live mode**
# (free DESTATIS GENESIS token). Pick one:
# 
# - **Snapshot mode (default):** leave `GENESIS_TOKEN` empty and Run All. Loads the
#   bundled CSV snapshot from this Lakehouse into Delta. ~1 minute.
# - **Live mode:** register at https://www-genesis.destatis.de/ → Profile → API-Token,
#   paste the token below, Run All. Pulls fresh data from the DESTATIS API and
#   enriches with Wikidata. ~10–15 minutes.
# 
# Either way: after this notebook finishes, open the **HochschulInsights** report.

# PARAMETERS CELL ********************

GENESIS_TOKEN = ""  # paste your DESTATIS GENESIS token here for live refresh

# CELL ********************

import notebookutils as nu

if GENESIS_TOKEN.strip():
    print("Token provided -> running live GENESIS load (10-15 min)")
    nu.notebook.run("hochschul_insights_genesis_loader",
                    arguments={"GENESIS_TOKEN": GENESIS_TOKEN, "useRootDefaultLakehouse": True})
    nu.notebook.run("hochschul_insights_genesis_dimensions",
                    arguments={"useRootDefaultLakehouse": True})
else:
    print("No token -> loading bundled snapshot from /Files/snapshot/")
    nu.notebook.run("hochschul_insights_load_snapshot",
                    arguments={"useRootDefaultLakehouse": True})

print("\nDone. Open the HochschulInsights report in this workspace.")

