# Hochschul-Insights — Power BI Report Plan

**Audience:** IT/data decision-makers in MinWiss, Hochschulleitung, Wissenschaftsministerien — plus the webinar crowd.
**Story angle:** *"Wo steht die deutsche Hochschullandschaft — und was kostet/erwirtschaftet sie?"*

## Source of truth & local working copy

The published model + report in the **Webinar** workspace is the source of truth.
Local edits happen in the OneDrive folder; backups go to the `pbir` backup store.

| Item | Value |
|---|---|
| Local working folder | `C:\Users\alkorn\OneDrive - Microsoft\Dokumente\03. Demo\Hochschul-Insights` |
| PBIP entry file | `Webinar Hochschule.pbip` |
| Report folder (PBIR) | `Webinar Hochschule.Report` |
| Semantic Model folder (TMDL) | `Webinar Hochschule.SemanticModel` |
| Workspace name | `Webinar` |
| Workspace ID | `9cf8322c-0c51-488c-a07b-b00449308809` |
| Workspace URL | https://app.powerbi.com/groups/9cf8322c-0c51-488c-a07b-b00449308809/list?ctid=fc3a8969-ed60-4daa-92df-1fdf4ff5bc15&experience=power-bi |
| Tenant ID | `fc3a8969-ed60-4daa-92df-1fdf4ff5bc15` (Fabric tenant — NOT corp) |
| Capacity | `9f769e20-125f-4fce-97a7-0ee3d505be89` (West US 3) |
| Report ID | `96c67c64-e2c3-4ea9-beb5-41c4335e1c67` (`Webinar Hochschule`) |
| Semantic Model ID | `f4b298e8-fd43-4de7-a2d5-40fbe141be98` (`Hochschule`) |
| Lakehouse | `WebinarLakehouse` (`5d5a8e6d-2745-4d5c-8bf2-032af3d32d43`) — Direct Lake source |

### Sync workflow (always round-trip; never edit out of sync)

The published version in the **Webinar** workspace and the local OneDrive copy must always match. Every working session is bookended by a sync — pull before any edit, publish immediately after.

**Before any edit (service → local):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\alkorn\repos\temp\download_hochschule_from_service.ps1
```

Overwrites both `Webinar Hochschule.Report\` and `Webinar Hochschule.SemanticModel\` with the live service definition (Fabric REST `getDefinition`). No `pbir`/`fab` CLI required.

**After every local edit (local → service):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\alkorn\repos\temp\publish_hochschule_to_service.ps1
```

Pushes both folders back via Fabric REST `updateDefinition` (SM first, then Report). Run this immediately after saving — do not stack multiple unsynced edits.

**Rules:**
- Never start an edit without pulling first.
- Never close an edit session without publishing.
- If pull and push happen out of order, the local file wins on the next push and overwrites unrelated service-side changes — so always pull → edit → push in one continuous flow.
- For semantic model edits made via TMDL only, [push_sm.ps1](../temp/push_sm.ps1) is a faster shortcut that skips the report.

---

## Design theme — derived from "Design for Education Demo.pptx" slide 41

Slide 41 is the **Hochschul-Insights brand title slide**. Use it as the visual anchor for the report theme.

| Token | Hex | Usage |
|---|---|---|
| Brand primary (deep teal-green) | `#147A67` | Page titles, KPI delta-positive, primary chart color, hyperlinks |
| Brand cream (warm) | `#FFF6DD` | Page background — bottom/right of canvas |
| Brand mint (pale turquoise) | `#DFF5E8` | Page background — top/left of canvas; soft card backgrounds |
| Neutral ink | `#1C1C1C` | Body text |
| Subdued grey | `#6B7280` | Axis labels, secondary text |
| Delta-negative | `#B83A3A` | YoY-Δ negative, Drittmittelquote unter Bundesschnitt |

**Background:** linear gradient `#DFF5E8` (top-left) → `#FFF6DD` (bottom-right) on every page — matches the slide deck.
**Logo:** "Hochschul-Insights" leaf/book mark from slide 41 placed top-left of every page (small, ~20×14 px).
**Typography:**
- Headings → `Segoe Sans Text Semibold` (fallback `Segoe UI Semibold`), color `#147A67`.
- Body → `Segoe UI`, 10–11pt, color `#1C1C1C`.
- KPI numbers → `Segoe UI Light`, 28pt, color `#147A67`.

**JSON theme file:** generate via `pbir theme build` and store at `Webinar Hochschule.Report/StaticResources/SharedResources/BuiltInThemes/HochschulInsights.json`. IBCS rules (signed numbers, Δ vs. Vorjahr) on top.

## Semantic Model — relationships

Calc dims auto-built via `DISTINCT()` from facts in TMDL. Bundesland-Geo via `dim_Hochschulen` Lat/Lon for institution map; for choropleth use a separate small `dim_BundeslandGeo` table (16 rows + ISO codes).

## Page 1 — Übersicht Deutschland (the headline page)

Goal: in 10 seconds: how many students, how much money, where is the trend going.

| Zone | Visual | Field |
|---|---|---|
| KPI row (4 cards) | Studierende aktuelles WS · Studienanfänger aktuelles WS · Gesamteinnahmen letzter Berichtsjahr · Drittmittelquote | with YoY-Delta |
| Map | Deutschlandkarte Bundesländer (choropleth: Studierende pro 1.000 Einwohner) | `dim_BundeslandGeo` |
| Trend | Liniendiagramm Studierende & Studienanfänger 2014–2024 | `Studierende`, `StudienanfaengerHochschule` |
| Stacked area | Einnahmen-Mix DE: Trägermittel · Drittmittel · Verwaltungseinnahmen · sonstige (aus Hochschulfinanzen) | `Hochschulfinanzen` |
| Top-N | Top-10 Hochschulen nach Studierendenzahl + Drittmitteleinnahmen | `Studierende`, `Drittmittel` (note: Drittmittel is BL-Ebene → hier nur Studierende-Ranking) |

**Slicer leiste oben:** Wintersemester / Berichtsjahr · Trägerschaft (staatlich/privat/kirchlich) (aus `dim_Hochschulen`)

## Page 2 — Studierende & Hochschulkarte

Story: Wer studiert was, wo, mit welcher Herkunft — und wo sitzen die Hochschulen.

**Linke Hälfte — Studierenden-Analyse:**

- Liniendiagramm Studierende-Trend × Nationalität (Deutsche vs Ausländer) — exakt warum wir die Insgesamt-Zeilen rausgefiltert haben.
- Säulendiagramm × Geschlecht im Zeitverlauf (Anteilsentwicklung).
- Treemap Fächergruppen (aus `StudierendeStudienfach`) — Größe = Studierende.
- Bar chart Top-20 Studienfächer absolute Studierende, mit Wachstumsrate-Datenbalken.
- Anfänger vs. Studierende Bestand-Verhältnis (= grobe Verweildauer-Proxy) je Bundesland.

**Rechte Hälfte — Hochschulkarte (eine der "wow"-Seiten für den Webinar-Demo):**

- Azure Map / Icon Map mit allen Hochschulen (Lat/Lon aus `dim_Hochschulen`) — Bubble-Size = Studierendenzahl, Farbe = Trägerschaft.
- Top-Liste aktuell sichtbarer Hochschulen mit Mini-Spark-Line unter der Karte.
- Hochschulen ohne Geo (`Source = null`) → "Unmapped"-Liste, damit transparent ist was fehlt.

**Cross-filter:** Klick auf eine Bubble filtert die Studierenden-Visuals links; Klick auf einen Trend-Punkt links filtert die Karte rechts. Klick auf Bubble + Drillthrough → Page "Hochschul-Detail".

**Slicer:** WS · Bundesland · Hochschulart · Trägerschaft · Geschlecht · Nationalität · Studierenden-Range Slider.

## Page 3 — Finanzen & Drittmittel

Story: Das Geld der Hochschulen.

- Waterfall Bundesland: Gesamteinnahmen → Trägermittel → Drittmittel → Sonstiges.
- Quadrant-Scatter: X = Trägermittel/Studierender · Y = Drittmittel/Studierender · Bubble = Studierendenzahl, eine Bubble pro Bundesland.
- Heatmap Drittmittelquote (Drittmittel / (Trägermittel + Drittmittel)) × Bundesland × Jahr.
- Stacked column Ausgaben-Struktur je Hochschulart × Fächergruppe.
- KPI-Cards: Bundesweite Drittmittelquote · höchster/niedrigster BL.

**Slicer:** Berichtsjahr · Bundesland · Hochschulart · Fächergruppe · Kennzahl.

## Page 4 — Personal & Forschung

Story: Wer lehrt und forscht.

- KPI: Hauptberufliches Personal · davon Wissenschaftler · davon Professor:innen · Frauenanteil Professur (mit Trend).
- Liniendiagramm Frauenanteil Professur × Fächergruppe (zeigt MINT-Lücke).
- Bar chart Personal pro 1.000 Studierende × Bundesland (Betreuungsquote).
- Stacked column Beschäftigungsverhältnis (befristet/unbefristet/teilzeit/vollzeit).
- Drittmittel pro wiss. VZÄ × Fächergruppe — Forschungsproduktivitäts-Proxy.

## Page 5 — Studienerfolg

Story: Was kommt am Ende raus (`PruefungenBL`).

- Funnel Anfänger → Studierende → Bestandene Prüfungen × Bundesland.
- Stacked column Prüfungsergebnisse (bestanden/nicht bestanden) × Studienfach.
- Erfolgsquote × Geschlecht × Nationalität (kann politisch heikel sein — vorsichtig kommentieren).
- Trend Erfolgsquote 5 Jahre.

## Page 6 — Hochschul-Detail (Drillthrough-Page)

Wird über Studierende-Page oder Karte angesteuert mit Hochschul-Code als Drillthrough-Filter.

- Header: Hochschulname, Bundesland, Trägerschaft, Gründungsjahr, Lat/Lon, Logo-Slot.
- Studierende-Trend, Anfänger-Trend, Geschlecht-Mix, Nationalitäts-Mix.
- Karte mit einzelner gepinter Bubble + Umkreissicht.
- Hinweis-Visual wenn `Source IS NULL` ("Stammdaten nicht verlinkt").

## Page 7 — Datenqualität & Quellen (kleiner Tab, hidden im Demo)

- Tabelle alle 12 Genesis-Codes mit Zeilenzahl + letztem Refresh.
- Anteil Hochschulen mit / ohne Wikidata-Match (`Source = C/A/null`).
- Hinweis auf DESTATIS-Lizenz (Datenlizenz Deutschland 2.0).

## Cross-cutting design rules

- **Theme:** corporate / IBCS-konform; signed numbers, Δ vs. Vorjahr immer sichtbar.
- **Slicer-Strategie:** WS / Berichtsjahr als Sync-Slicer über alle Seiten in einem Filter-Pane.
- **Direct Lake** auf den Lakehouse-Tabellen — kein Import nötig.
- **Bookmarks:** "Webinar-Story" mit 3–4 Schritten für Live-Demo (Übersicht → Karte → Detail-Hochschule → Finanzen).
- **Tooltips als Pages:** Mini-Hochschulkarte als Tooltip-Page, hover über Bubble.

## Quick wins für den Webinar-Pitch

1. **Map mit Drillthrough** — visuell stark, Direct-Lake-Performance erlebbar.
2. **Drittmittelquote-Heatmap** — Story + politisch interessant.
3. **Frauenanteil Professur × Fach** — diversity story.
4. **Anfänger-vs-Bestand-Quotient** — neue Metrik, aus zwei Tabellen kombiniert.


---

## Backlog — Report Improvement Ideas (intake 2026-05-18)

Source: `pbi-report-improvement-notes.md` (working notes from Webinar Hochschule report improvement session). To be prioritized.

### Ideas

#### HTML companion website
- Landing site for the report (documentation, KPI definitions, user guide).
- Could host embedded report or link to Power BI service.
- Open question: purpose — public-facing showcase, internal docs, or report container?

#### Injae Park IBCS custom visual
- Evaluate Injae Park's IBCS-compliant custom visual against current visuals (variance charts, structure compliance).
- Check certification status, performance, licensing.
- Potential fit with PBI Fixer Feature 70 (IBCS Variance Charts) and Feature 89 (Fix All Charts) — if certified + performant, could become alternative output of `fix_ibcs_variance()`.

#### Jumpstart script
- Reusable bootstrap script applied on import/open of the report.
- Standard cleanup operations baked in (theme, page size, IBCS basics, Fix All).
- Candidate for a new PBI Fixer preset (e.g. "Jumpstart").

#### Basic clean up of file
- Hygiene pass: unused columns/measures, hidden tech tables, descriptions, display folders.
- Consistent formatting strings, naming conventions.
- Remove orphaned visuals, unused bookmarks, dead pages.

#### Include items in PBI Fixer
- Wire identified fixes/cleanups as fixers.
- Extend BPA auto-fixers and report fixers inventory.
- Gaps to evaluate vs current Fix_* set: orphaned visual removal, dead-page removal, unused-bookmark removal — none currently shipped.

#### AI agent on top of report
- Copilot / custom agent over the semantic model.
- Natural-language Q&A.
- Potentially leverage SLL AI patterns (Michael Kovalsky reference).
- Tie-in with planned PBI Fixer AI assistant window.

#### DEV / QA environment
- Proper DEV → QA → PROD deployment pipeline.
- Workspace separation, deployment rules, parameterized data sources.
- Source control (PBIR + Git).
- Promotion criteria / review gates.

### Next steps
- [ ] Prioritize items above
- [ ] Clarify scope of HTML companion website
- [ ] Evaluate Injae Park visual hands-on
- [ ] Draft jumpstart script outline (preset definition)
- [ ] Expand "basic clean up" into a concrete checklist
- [ ] Map each cleanup item to either an existing PBI Fixer fixer or a new `_Fix_*` / `_Add_*` entry
