# Hochschul-Insights → Fabric Jumpstart Plan

Target: contribute `hochschul-insights` to [microsoft/fabric-jumpstart](https://github.com/microsoft/fabric-jumpstart) as a **community** Jumpstart.

## TL;DR — Two install modes

```python
import fabric_jumpstart as jumpstart

# Mode 1: zero-config — deploys items + auto-uploads bundled CSV snapshot
jumpstart.install("hochschul-insights")

# Mode 2: live refresh — same install, then user pastes GENESIS token into
# the entry-point notebook (parameter cell) and runs it
```

> Note: the `fabric-jumpstart` Python API does **not** support passing arbitrary
> jumpstart-specific arguments. Documented kwargs are only:
> `workspace_id`, `overwrite`, `auto_prefix_on_conflict`, `item_prefix`,
> `unattended`, `repo_ref`. The token must therefore be provided **inside the
> deployed notebook**, not as an `install()` argument.

---

## 0. Pre-work — SECURITY (resolved 2026-05-21)

- [x] Old GENESIS token rotated at https://www-genesis.destatis.de → Profile → API-Token.
- [x] Old token scrubbed from working tree (5 GENESIS Loader notebooks + Playwright capture artifacts).
- [x] Verified old token never committed to `KornAlexander/Fabric-Notebooks` (notebooks were untracked) — no git history rewrite needed.
- [ ] Going forward: **never paste the new token into any file**. Use an environment variable (`$env:GENESIS_TOKEN`) or Fabric Variable Library / Key Vault reference, and pass it into the notebook via a Parameters cell at runtime.

## 1. Repo layout — new public repo

Jumpstart standards require a **lightweight, self-contained repo** pinned to a
git tag. Recommended: new public repo `alkorn/hochschul-insights` (or under a
Microsoft org if co-owner provides it).

```
hochschul-insights/                      <- new public repo, MIT licensed
├── README.md                            <- install instructions, screenshots, data lineage
├── LICENSE                              <- MIT
├── data/
│   ├── snapshot/                        <- bundled CSVs uploaded to Lakehouse on install
│   │   ├── fact_studierende.csv
│   │   ├── fact_absolventen.csv
│   │   ├── fact_personal.csv
│   │   ├── fact_drittmittel.csv
│   │   ├── dim_hochschule.csv
│   │   ├── dim_fach.csv
│   │   ├── dim_bundesland.csv
│   │   ├── dim_zeit.csv
│   │   └── ... (10 fact + ~6 dim tables)
│   └── manifest.json                    <- {snapshot_date, genesis_tables, row_counts}
├── workspace/                           <- mirror of Fabric workspace, committed via Git Integration
│   └── hochschul-insights/              <- top-level folder == logical_id (Jumpstart requirement)
│       ├── hochschul_insights_lh.Lakehouse/
│       ├── 00_start_here.Notebook/                <- entry_point
│       ├── hochschul_insights_genesis_loader.Notebook/
│       ├── hochschul_insights_genesis_dimensions.Notebook/
│       ├── hochschul_insights_load_snapshot.Notebook/   <- NEW: reads /Files/snapshot/*.csv into Delta
│       ├── HochschulInsights.SemanticModel/
│       └── HochschulInsights.Report/
└── scripts/
    └── refresh_snapshot.py              <- local helper: runs loader, exports CSVs, commits to data/snapshot/
```

Rules from STANDARDS.md:
- Top-level workspace folder name MUST equal `logical_id` = `hochschul-insights`.
- Item names: `lower_case_snake_case` or `ProperCamelCase`, **no spaces**.
- → Rename your current `Hochschul-Insights GENESIS Loader.ipynb` →
  `hochschul_insights_genesis_loader.Notebook`. Same for Dimensions.
- `repo_ref` must be a commit SHA or tag (e.g. `v1.0.0`) — **no branch refs**.

## 2. Notebook changes

### 2.1 New notebook: `00_start_here` (entry_point)

Markdown-heavy welcome notebook. One parameter cell, one router cell.

```python
# === Parameters (mark this cell as "Parameters" in the notebook properties) ===
GENESIS_TOKEN = ""   # paste your token to enable live refresh; empty = use bundled snapshot
```

```python
# === Router ===
import notebookutils as nu
if GENESIS_TOKEN.strip():
    print("Token provided → running live GENESIS load (10–15 min)")
    nu.notebook.run("hochschul_insights_genesis_loader", arguments={"GENESIS_TOKEN": GENESIS_TOKEN})
    nu.notebook.run("hochschul_insights_genesis_dimensions")
else:
    print("No token → loading bundled snapshot from /Files/snapshot/")
    nu.notebook.run("hochschul_insights_load_snapshot")
print("Done. Open the HochschulInsights report.")
```

Markdown sections required by STANDARDS.md:
- Name + objectives of the Jumpstart
- Two-mode explanation (snapshot vs live) with the destatis registration link
- Where to find the deployed report (dynamic link using `nu.runtime.context`)
- Snapshot date from `manifest.json`

### 2.2 New notebook: `hochschul_insights_load_snapshot`

Small, ~30 lines. Reads every CSV under `Files/snapshot/` and writes to Delta
with the same table names the semantic model expects. No external calls,
runs in <1 minute.

```python
import os, pandas as pd
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
SNAP = "Files/snapshot"
for f in os.listdir(f"/lakehouse/default/{SNAP}"):
    if not f.endswith(".csv"): continue
    table = f.removesuffix(".csv")
    df = pd.read_csv(f"/lakehouse/default/{SNAP}/{f}")
    spark.createDataFrame(df).write.mode("overwrite").format("delta").saveAsTable(table)
    print(f"  loaded {table}: {len(df):,} rows")
```

### 2.3 Modify: `hochschul_insights_genesis_loader`

- [ ] **Remove hardcoded token** (line 87).
- [ ] Convert the `GENESIS_TOKEN = "..."` cell into a **Parameters cell** with
  empty default.
- [ ] Add guard at top:
  ```python
  if not GENESIS_TOKEN.strip():
      raise ValueError("GENESIS_TOKEN not set — open 00_start_here and paste your token there.")
  ```
- [ ] No other behavioural changes.

### 2.4 Modify: `hochschul_insights_genesis_dimensions`

- [ ] No token needed (it enriches via Wikidata + Lakehouse reads). Verify it
  reads from the same table names the snapshot loader writes.
- [ ] If it currently depends on outputs only the GENESIS loader produces,
  ensure the snapshot CSVs cover those columns too.

## 3. Snapshot data preparation

One-time + periodic:

1. Run `scripts/refresh_snapshot.py` locally (or in a Fabric notebook):
   - Uses YOUR rotated GENESIS token (from env var, never committed).
   - Runs the loader logic, exports each Delta table to CSV in `data/snapshot/`.
   - Updates `data/manifest.json` with `{snapshot_date, row_counts, genesis_tables}`.
2. Commit + push.
3. Tag a release (`v1.0.0`, `v1.1.0`, …) — Jumpstart pins to the tag.

Cadence: quarterly is fine for hochschul data (DESTATIS publishes yearly).

Size budget: keep `data/snapshot/` under ~50 MB so cloning stays fast. If a
fact table is too big, ship aggregated/sampled and document it in
`manifest.json`.

## 4. YAML registration (the actual PR to fabric-jumpstart)

Fork `microsoft/fabric-jumpstart`, create
`src/fabric_jumpstart/fabric_jumpstart/jumpstarts/community/hochschul-insights.yml`:

```yaml
id: <next-available-positive-int>          # check existing IDs
logical_id: hochschul-insights
name: Hochschul-Insights (German Higher Education)
description: >
  End-to-end analytics on German higher-education data from DESTATIS GENESIS:
  students, graduates, staff, third-party funding — 10 fact + 6 dim tables,
  Direct Lake semantic model, Power BI report. Bundled snapshot included; live
  refresh optional via free GENESIS API token.
date_added: 05/21/2026
workload_tags:
  - Data Engineering
  - Power BI
scenario_tags:
  - Analytics
  - Public Sector
  - Education
type: Demo
source:
  repo_url: https://github.com/alkorn/hochschul-insights
  repo_ref: v1.0.0                                  # pin to tag, never a branch
  workspace_path: workspace/hochschul-insights
  files_source_path: data/snapshot/                 # auto-uploaded after deploy
  files_destination_lakehouse: hochschul_insights_lh
  files_destination_path: snapshot/                 # → /Files/snapshot/*.csv
items_in_scope:
  - Lakehouse
  - Notebook
  - SemanticModel
  - Report
entry_point: 00_start_here.Notebook
owner_email: fabricjumpstart.hochschul-insights@microsoft.com   # M365 group, created in step 6
mermaid_diagram: |
  graph LR
    SNAP[bundled snapshot CSVs]:::U1F4BE --> LH[hochschul_insights_lh]:::Lakehouse
    GENESIS[DESTATIS GENESIS API]:::U2601 -.-> LDR[hochschul_insights_genesis_loader]:::Notebook
    LDR --> LH
    SS[00_start_here]:::Notebook --> LDR
    SS --> LSS[hochschul_insights_load_snapshot]:::Notebook
    LSS --> LH
    LH --> SM[HochschulInsights]:::SemanticModel
    SM --> RPT[HochschulInsights]:::Report
```

Validate locally:
```powershell
cd src/fabric_jumpstart
uv run pytest tests/test_registry.py
```

## 5. README modifications

### 5.1 New repo `hochschul-insights/README.md`

Sections:
- Hero + screenshot of the Power BI report
- **One-line install**: `jumpstart.install("hochschul-insights")`
- **Two modes** table (snapshot vs live) with what each gives you and how long it takes
- **GENESIS token** section: free, link to registration, where to paste it
- **What's inside**: table inventory, model diagram, sample DAX
- **Data lineage / snapshot date** — pulled from `manifest.json`
- **Limitations** (free token: no PER_BL_PER_YEAR tables, snapshot quarterly)
- **License**: MIT, data attribution to DESTATIS (CC-BY)
- Link back to fabric-jumpstart

### 5.2 Existing `Hochschul-Insights/PowerBI-Report-Plan.md` and `Customer-Demo-Patterns.md`

- [ ] Leave in private repo. Do **not** move to public repo.
- [ ] Add note at top: "Public Jumpstart variant lives at
  `https://github.com/alkorn/hochschul-insights` — see JUMPSTART-PLAN.md."

### 5.3 This repo's `Hochschul-Insights/JUMPSTART-PLAN.md` (this file)

Keep updated as the source of truth for the public-repo workflow.

## 6. M365 group + Fabric workspace (co-owner step)

- [ ] Ask MS co-owner to request M365 group
  `fabricjumpstart.hochschul-insights@microsoft.com` via idweb / MyAccess.
- [ ] Add yourself + co-owner as group owners.
- [ ] Create Fabric workspace `jumpstart.hochschul-insights`.
- [ ] Make the M365 group workspace admin.
- [ ] Connect workspace to the public GitHub repo via Git Integration (PAT with
  Content permissions).
- [ ] Commit all Fabric items from the workspace to the repo's
  `workspace/hochschul-insights/` folder.

## 7. Local validation before PR

```python
import fabric_jumpstart as js
js.install("hochschul-insights",
           workspace_id="<test-workspace-guid>",
           repo_ref="v1.0.0")
# Expected: items deploy, snapshot CSVs auto-upload, 00_start_here runs end-to-end
# with empty token in <2 min and report renders on bundled data.
```

Then with token:
- Open `00_start_here`, paste token, run all. Live refresh completes,
  Delta tables overwritten with fresh GENESIS data, report still works.

## 8. PR submission

1. Issue first (`New Jumpstart` template) — describe the two-mode design,
   flag the snapshot+token approach explicitly for `@mwc360` to approve.
2. PR title: `feat: add hochschul-insights jumpstart` (Conventional Commits).
3. Include: filled YAML, generated diagram SVGs (light+dark) in
   `assets/images/diagrams/`, link to the public hochschul-insights repo at
   the pinned tag, link to a successful local test run.

## 9. Open questions for the maintainer issue

1. Is the **bundled-snapshot + optional-live-refresh** pattern acceptable for
   community Jumpstarts that depend on a registration-only API?
2. Any size limit on `files_source_path` payloads (estimating ~30 MB)?
3. Recommended snapshot refresh cadence / automation (GH Action allowed)?
4. Can a community Jumpstart use a personal GitHub repo as `repo_url`, or must
   it sit under a Microsoft org?

## Checklist (high-level)

- [ ] Rotate leaked GENESIS token + scrub git history
- [ ] Create new public repo `hochschul-insights`
- [ ] Restructure: workspace folder, data/snapshot, scripts
- [ ] Refactor notebook names (no spaces, snake_case)
- [ ] Remove hardcoded token from loader, convert to Parameters cell
- [ ] Build `00_start_here` router notebook
- [ ] Build `hochschul_insights_load_snapshot` notebook
- [ ] Generate initial snapshot CSVs + manifest.json
- [ ] Tag `v1.0.0`
- [ ] Create M365 group + Fabric workspace + Git Integration (needs co-owner)
- [ ] Write YAML + validate with `pytest tests/test_registry.py`
- [ ] Generate mermaid SVGs (light + dark)
- [ ] Local end-to-end install test, both modes
- [ ] Open `New Jumpstart` issue
- [ ] Submit PR
