# Education / Hochschul-Insights — Slim Report Plan (Demo Workspace)

**Target workspace:** `Demo` (`da2e15a8-c06d-4da0-ad10-c68aba63e564`), folder **Education** (`282c7964-10fb-4fb2-a50a-e9f582c84182`)
**Lakehouse:** `DemoLakehouse` (`4317e2f8-18dc-4490-8a43-b564dc6a698e`), schema `genesis`
**Story:** *"Vom DESTATIS-Datensatz zum Live-Insight — Architektur first, Inhalt second."*
**Audience:** Hochschul-IT, Wiss-Ministerien, Webinar — same as the original Hochschul report, but condensed for a 10-minute demo.

> Sister deliverable to [`PowerBI-Report-Plan.md`](PowerBI-Report-Plan.md) (8-page Webinar Hochschule). This plan keeps the same look & feel but trims to **4 pages**.

---

## Status check — Lakehouse data (2026-05-21)

All loader/dimensions notebooks landed cleanly. `Tables/genesis/` contains **16 Delta tables**, last refresh **2026-05-18 14:48 UTC**:

| Layer | Tables (Delta, schema `genesis`) |
|---|---|
| **Facts (10)** | `studierende`, `studierendebund`, `studienanfaengerhochschule`, `hochschulfinanzen`, `ausgaben`, `einnahmen`, `drittmittel`, `hochschulpersonal`, `wisspersonalfach`, `professoren` |
| **Dims (6)** | `hochschulen`, `bundesland`, `hochschulart`, `faechergruppe`, `geschlecht`, `nationalitaet` |

Parquet present and non-trivial — biggest table `studierende` (~7.9 MB across 359 files; OPTIMIZE pending), `hochschulen` ~3.4 MB (Wikidata-enriched), all dims under 120 KB. Notebook artifacts in workspace:

- Notebook `Hochschul-Insights GENESIS Loader` (`ef458d26-…`)
- Notebook `Hochschul-Insights GENESIS Dimensions` (`9345154d-…`)
- DataPipeline `Hochschul-Insights GENESIS Pipeline` (`5a677558-…`)
- SemanticModel `Hochschule` (`6a64b144-…`) — **exists, reuse as Direct Lake source**
- Report `Webinar Hochschule` (`a30522c1-…`) — exists in Education folder; use as visual reference

**Action:** new slim report → new SemanticModel `Hochschule Demo Slim` (or reuse `Hochschule`) → 4-page report `Hochschul-Insights Demo`.

---

## Design theme (re-use from main plan)

Same brand tokens as [`PowerBI-Report-Plan.md`](PowerBI-Report-Plan.md):

- Primary teal-green `#147A67`, mint `#DFF5E8`, cream `#FFF6DD`
- Gradient background mint → cream on every page
- Heading: Segoe Sans Text Semibold; KPI numbers Segoe UI Light 28pt
- IBCS signed-delta rules (▲ green `#147A67`, ▼ red `#B83A3A`)

---

## Semantic model (Direct Lake)

Reuse the existing `Hochschule` model where possible. Star schema, all relationships single-direction, all dims `*-1` to facts.

```
            ┌─ bundesland (16)
            │
hochschulen ┴─ hochschulart   ┐
                              │
faechergruppe ─┐              ├─ FACT tables
geschlecht ────┤              │     studierende, studierendebund,
nationalitaet ─┤              │     studienanfaengerhochschule,
               └──────────────┘     hochschulfinanzen, ausgaben,
                                    einnahmen, drittmittel,
                                    hochschulpersonal, wisspersonalfach,
                                    professoren
```

Core measures (all live in `Measure` table):

| Measure | Formula | Format |
|---|---|---|
| `# Studierende` | `SUM(studierende[Wert])` | `#,##0` |
| `# Studienanfänger` | `SUM(studienanfaengerhochschule[Wert])` | `#,##0` |
| `# Professoren` | `SUM(professoren[Wert])` | `#,##0` |
| `Frauenanteil Prof %` | `DIVIDE(CALC(..., geschlecht="weiblich"), [# Professoren])` | `0.0%` |
| `Ausländer-Anteil %` | `DIVIDE(CALC(..., nationalitaet="Ausländer"), [# Studierende])` | `0.0%` |
| `Hochschulausgaben €` | `SUM(ausgaben[Wert_EUR])` | `€ #,##0` |
| `Drittmittel €` | `SUM(drittmittel[Wert_EUR])` | `€ #,##0` |
| `Drittmittelquote %` | `DIVIDE([Drittmittel €], [Hochschulausgaben €])` | `0.0%` |
| `Studierende YoY %` | `DIVIDE([# Studierende] - [# Studierende PY], [# Studierende PY])` | `+0.0%;-0.0%` |

---

## Page 1 — Übersicht Deutschland

**Goal:** answer "Wie groß ist die deutsche Hochschullandschaft heute?" in 10 seconds.

| Slot | Visual | Fields |
|---|---|---|
| Header strip | Title `Hochschul-Insights — Deutschland`, year slicer (single-select, default = latest) | `studierende[Jahr]` |
| KPI row (4) | Cards | `# Studierende`, `# Hochschulen`, `Hochschulausgaben €`, `Drittmittelquote %` (each with YoY-Δ) |
| Map (left half) | Filled map (Bundesländer) | `bundesland[Bundesland]` + `# Studierende` color scale `#DFF5E8 → #147A67` |
| Trend (top-right) | Line chart | `# Studierende` by `studierende[Jahr]`, split by `hochschulart[Hochschulart]` |
| Mix (bottom-right) | 100% stacked bar | Einnahmen-Quellen aus `einnahmen` by `einnahmen[Position]` |

---

## Page 2 — Studierende & Studienanfänger

**Goal:** Diversität & Fächerverteilung.

| Slot | Visual | Fields |
|---|---|---|
| KPI row (3) | Cards | `# Studienanfänger`, `Ausländer-Anteil %`, `Frauenanteil Studierende %` |
| Trend left | Stacked area | `# Studierende` by `Jahr`, split by `nationalitaet[Nationalitaet]` |
| Treemap right | Treemap | `# Studierende` by `faechergruppe[Faechergruppe]`, color by `Studierende YoY %` |
| Bar bottom | Clustered bar (Top 15) | `hochschulen[Hochschule]` × `# Studierende`, filter latest year |

Drillthrough target: Page 4 (Hochschul-Detail).

---

## Page 3 — Finanzen & Personal

**Goal:** Wer gibt wieviel aus — und wie steht es um Drittmittel & Betreuung?

| Slot | Visual | Fields |
|---|---|---|
| KPI row (3) | Cards | `Hochschulausgaben €`, `Drittmittel €`, `Drittmittelquote %` (vs. Bundesschnitt) |
| Waterfall | Waterfall | Personal/Sach/Investitionen aus `ausgaben` by `ausgaben[Position]`, latest year |
| Heatmap | Matrix | Rows `bundesland`, Cols `Jahr`, Values `Drittmittelquote %`, conditional formatting mint→teal |
| Scatter bottom-right | Scatter | X = `Hochschulausgaben € / Studierender`, Y = `Drittmittelquote %`, Size = `# Studierende`, Color = `hochschulart`, Detail = `hochschulen[Hochschule]` |

---

## Page 4 — Hochschul-Detail (Drillthrough)

**Goal:** Drillthrough von Page 1–3 auf eine einzelne Hochschule.

| Slot | Visual | Fields |
|---|---|---|
| Header card | Hochschule name + Bundesland + Trägerschaft | `hochschulen[Hochschule]`, `[Bundesland]`, `[Hochschulart]` |
| KPI row (4) | Cards | `# Studierende`, `# Professoren`, `Drittmittel €`, `Frauenanteil Prof %` |
| Trend | Line | `# Studierende` × `Jahr` |
| Fächer mix | Donut | `# Studierende` by `faechergruppe` |
| Geo card | Azure Map (single pin) | `hochschulen[Lat]`, `hochschulen[Lon]` |
| Back button | Native button to source page | — |

Drillthrough filter: `hochschulen[Hochschule]`.

---

## Build sequence (≤ 1 hour)

1. **Duplicate** existing `Hochschule` semantic model in workspace → rename `Hochschule Demo Slim`, repoint to `DemoLakehouse / genesis` (already is).
2. Add/confirm the 9 core measures above (most already exist on `Hochschule`).
3. Create new report `Hochschul-Insights Demo` in the **Education** folder (`pbir new` locally, or duplicate the existing `Webinar Hochschule`).
4. Strip down to 4 pages, apply theme JSON, set drillthrough.
5. Publish via Fabric REST `updateDefinition` (use the existing `temp\publish_hochschule_to_service.ps1` pattern, retarget workspace+IDs).
6. Smoke test: slicer year change, drillthrough on a Top-15 bar, Bundesland filter → all visuals respond < 2 s (Direct Lake).

---

## Out of scope (kept in the 8-page plan)

- Pages: Hochschulkarte, Personal & Forschung, Studienerfolg, Datenqualität.
- Custom IBCS pyramid visuals.
- RLS / OLS (Demo workspace doesn't need it).
- Pipeline scheduling — already covered by `Hochschul-Insights GENESIS Pipeline`.
