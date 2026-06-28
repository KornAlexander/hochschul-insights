# DESTATIS GENESIS as a Customer Demo Pattern

The Hochschul-Insights notebook is one concrete example. The same skeleton works for almost any Microsoft customer in Germany — GENESIS-Online has **~30,000 published tables across ~250 statistics**, all under **Datenlizenz Deutschland 2.0** (commercial use allowed with attribution), all behind the **same REST API** the Hochschul-Insights loader already uses. Pattern is repeatable: swap the table codes + shapers, reuse everything else.

## Customer mappings

| Customer profile | Statistik | Story |
|---|---|---|
| Automotive (BMW, Mercedes, VW, Conti) | 45341 KFZ-Zulassungen, 51000 Außenhandel, 42121 Produktionserhebung | Marktanteile, Exportabhängigkeit, BEV-Quote |
| Pharma / Healthcare (Bayer, Roche, Sana, Helios) | 23211 Krankenhausstatistik, 23631 Pflegestatistik, 12613 Sterbefälle, 23131 Diagnosedaten | Versorgungsdichte, Pflegelücke, Demografie |
| Defense (BWI, Hensoldt, Rheinmetall) | 12411 Bevölkerung, 51000 Außenhandel Rüstung, 42221 Beschäftigte VG | Kapazität, Standorte, Lieferketten |
| Retail / FMCG (Edeka, Rewe, Aldi, Lidl) | 45212 Einzelhandel, 61111 VPI, 12211 Mikrozensus Haushalte | Umsatztrend, Kaufkraft, Konsumstruktur |
| Banking / Insurance (DZ, Allianz, Munich Re) | 81000 VGR, 61121 HVPI, 12612 Geburten, 12211 Haushalte | Makro-Indikatoren, Risikomodellierung |
| Telco (DTAG, Vodafone, O2) | 52911 IKT in Unternehmen, 12211 Haushalte mit Internet, 81000 VGR Branchen | Penetration, Investitionsbedarf |
| Energy / Utilities (E.ON, EnBW, Vattenfall, Stadtwerke) | 43311 Energiebilanzen, 43531 Erneuerbare, 32111 Wasser/Abwasser | Versorgungsmix, ESG, Kapazitätsplanung |
| Logistics (DHL, Schenker, Kühne+Nagel) | 51000 Außenhandel, 46xxx Verkehr, 42xxx Produktion | Frachtaufkommen, Routen, saisonale Spitzen |
| Real Estate (Vonovia, LEG, Deka) | 31231 Baufertigstellungen, 12411 Bevölkerung × Kreis, 61261 Mietenindex | Marktdruck, Standortbewertung |
| Public Sector (Länder, Kommunen, Ministerien) | depending — Bildung (211xx, 213xx), Soziales (22xxx), Justiz (243xx), Wahlen (14xxx) | reine Steuerungsdaten, perfect für Direct-Lake-Story |
| Education (TU Berlin, Fraunhofer, KIT) | exactly the current Hochschul-Insights | already built ✔ |
| Insurance underwriting | 41112 Erntestatistik (Agro), 23111 Todesursachen, 46xxx Unfälle | Pricing-Modelle |

## Practical tips

- **Keep the same skeleton** (config → fetch → shape → write → dim enrichment → demo). Swap only `TABLES` + the per-cube shapers — ~80% reuse per customer.
- **Build a lookup notebook** that hits `/catalogue/tables` with a search term so you can find candidate cubes in 10 seconds (e.g. `term=krankenhaus`).
- **Licensing for customer-facing work**: Datenlizenz Deutschland 2.0 is fine for Microsoft demos and customer prototypes. For productive customer dashboards, attribute `"Datenquelle: Statistisches Bundesamt (Destatis), <Jahr>"`.
- **International reuse**: Eurostat (`ec.europa.eu/eurostat`) and OECD use the same SDMX/REST pattern — same playbook works for global customers.

## Webinar "Aha" moment

> *"What you saw with Hochschulen — same approach works for any Destatis dataset, ~30k tables, free, public, your customer's KPIs are likely already in there."*
