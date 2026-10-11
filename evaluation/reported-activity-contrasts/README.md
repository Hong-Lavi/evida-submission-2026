# Compare the original reported concentrations

EVIDA puts two source measurements beside a deterministic concentration contrast, so a researcher can immediately inspect what was reported for the same compound against two targets. Every pair keeps its document, source record, structure, assay, units and unresolved conditions.

The calculation divides the comparator concentration by the reference concentration, then takes its base-10 logarithm. The general product function accepts explicitly selected saved rows for two targets and one endpoint. Matching source identity and stereochemistry precedes arithmetic; source inequalities retain their open or closed bounds. A retained assay response supports a condition match, while an unverified copy remains visibly unverified.

This development replay uses preserved ChEMBL IC50 records for PDE4B and PDE4D. All 221 source-record pairs from 219 groups are included. The native pilot is the preselected largest document/assay group: 42 of those same pairs, from [DOI 10.1016/j.bmcl.2013.12.076](https://doi.org/10.1016/j.bmcl.2013.12.076).

| Check | Denominator | Observed result |
|---|---:|---|
| Preserved v1 arithmetic | 221 pairs / 219 groups | 221 exact contrasts; separate arithmetic checks agree |
| Native v2 product path | 42-pair subset | 42 completed; original values, contrasts, directions and unresolved conditions agree |
| Condition interpretation | All 221 pairs | Incomplete protocol information remains unknown |
| Three reports for one structure | 3 source records | Ratios 1.4, 1.20689655 and 3 remain separate |
| Two descriptive orderings in the pilot | 42 pairs | Both begin with CHEMBL3114956: 3.0 versus 1300 nM, ratio 433.33 |

The comparison adds inspectable arithmetic to the original-record display. The reference-IC50-only and ratio-only orderings have the same first candidate here. These are development checks of reported concentrations and source binding; biological selectivity requires evidence for the applicable assay conditions.

**Recalculate the preserved values with Python alone:**

```sh
python scripts/verify_manifest.py
python scripts/verify_arithmetic.py
```

The verifier uses exact rational concentration arithmetic independently of the product code. [pairs.csv](data/pairs.csv) gives the complete ledger; deduplicated measurements, assays and document DOIs are in `data/`. Original API URLs, collection dates and response hashes are in [source-pins.json](source-pins.json). The API snapshot was collected on 2026-10-01; its database release number was not captured.

The exact v1 and v2 calculation modules, native integration patch and environment pins support code inspection. [METHOD.md](METHOD.md), [REPRODUCTION.md](REPRODUCTION.md) and [review resolutions](receipts/independent-review-v2.json) distinguish the 221-pair arithmetic check from the v2 assay-binding checks on its 42-pair subset. The two review findings—condition-copy authority and decimal precision—are retained with their resolutions.

The next useful step is to inspect the two original assay descriptions and choose a comparable follow-up measurement for candidates relevant to the research goal. [ChEMBL attribution and data terms](NOTICES.md) accompany the selected records and derived contrasts.
