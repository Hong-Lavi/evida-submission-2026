# Data and software notices

The selected curated measurements, assay descriptions/metadata and document identifiers come from **ChEMBL, EMBL-EBI**, https://www.ebi.ac.uk/chembl/. The records were collected through the public API on 2026-10-01. The contemporaneous database release number was not captured; `source-pins.json` records the exact response URLs, collection timestamps and SHA256 hashes. Per-document initial-release fields retain their original meaning.

The ChEMBL-derived data and contrast tables in `data/` are distributed under **Creative Commons Attribution–ShareAlike 3.0 Unported (CC BY-SA 3.0)**. Preserve the attribution, license link and change notice when redistributing these data or adaptations. The package selects and deduplicates scientific fields, joins retained assay/document metadata, and adds ratio/log10 results and provenance annotations. ChEMBL/EMBL-EBI endorsement is not implied.

- [ChEMBL official website: data license](https://www.ebi.ac.uk/chembldb/)
- [ChEMBL official FAQ: licensing and releases](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/general-questions)
- [CC BY-SA 3.0 license deed](https://creativecommons.org/licenses/by-sa/3.0/)
- [CC BY-SA 3.0 legal text](https://creativecommons.org/licenses/by-sa/3.0/legalcode)
- [EMBL-EBI Terms of Use](https://www.ebi.ac.uk/about/terms-of-use/)

ChEMBL's FAQ permits use, redistribution and adaptation with attribution and share-alike terms. It separately identifies commercially derived compound-property calculations; this projection contains reported activity and assay records, rather than those property calculations. EMBL-EBI's terms retain the rights of original data owners. The original publications are attributed by their document IDs and DOIs, and their abstracts/full text are not reproduced here.

Please cite ChEMBL: Zdrazil B et al. (2024), Nucleic Acids Research 52(D1), D1180–D1192, [doi:10.1093/nar/gkad1004](https://doi.org/10.1093/nar/gkad1004). For the API: Davies M et al. (2015), Nucleic Acids Research 43(W1), W612–W620, [doi:10.1093/nar/gkv352](https://doi.org/10.1093/nar/gkv352).

The calculation modules, verification scripts and integration patch are EVIDA-authored code. This package does not assign a new blanket software license or change the containing repository's software terms. Imported third-party packages are identified in `environment.json`; their implementations, compiled runtimes and model weights are not bundled. The data's CC BY-SA notice is scoped to the data and derived tables.

The official rights pages were checked on 2026-10-11. `rights-sources.json` identifies the evidence and the available scope.
