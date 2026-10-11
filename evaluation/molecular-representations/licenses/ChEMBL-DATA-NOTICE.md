# ChEMBL-derived data attribution

The prepared MoleculeACE assay tables derive from ChEMBL, maintained by EMBL-EBI and its contributors. ChEMBL curates reported bioactivities from the primary scientific literature. This package does not grant a new MIT license to the underlying ChEMBL database content.

ChEMBL makes its data available under the [Creative Commons Attribution-ShareAlike 3.0 Unported license](https://creativecommons.org/licenses/by-sa/3.0/). Preserve that attribution and the applicable ShareAlike terms for redistributed adaptations of the data. The [official ChEMBL data-licensing statement](https://chembl.gitbook.io/chembl-interface-documentation/about#data-licensing) was checked during package review on 2026-10-11; no database download or new scientific query was made for this check.

Data here passed through the pinned MoleculeACE benchmark preparation, official train/test assignment and pKi/pEC50 values. EVIDA then assigned traceable candidate IDs, separated test features from evaluation-only labels, and formed an inner Murcko-scaffold training/validation partition. These are adaptations of the supplied benchmark tables, not new experimental measurements. `dataset-pins.json` identifies the benchmark commit, source CSV digests, task IDs, preparation conventions and prepared-file hashes. ChEMBL release information not recorded by the upstream preparation is not invented here.

MoleculeACE's repository MIT notice is retained separately as `MoleculeACE-LICENCE.txt`; CheMeleon code uses its own MIT notice. Neither software notice overrides rights in underlying data, articles or third-party models. No underlying journal articles are redistributed by this package.
