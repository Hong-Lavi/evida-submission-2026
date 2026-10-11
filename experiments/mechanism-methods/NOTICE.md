# Source and license notices

- [Caspo author source](https://github.com/bioasp/caspo/tree/45b41124ab933996687f1e0581a4f15b32e7806f) is GPL-3.0-or-later. The copied Toy fixture inputs come from that repository; its license text is [included](licenses/CASPO-GPL-3.0.txt). No caspo implementation files or encodings are copied.
- [CORNETO author source](https://github.com/saezlab/corneto/tree/d9f6d238d6c41cc20ecc0b4a17d105cbf209b360) declares GPL-3.0-or-later; its license text is [included](licenses/CORNETO-GPL-3.0.txt). The packaged synthetic case specifications are EVIDA-authored, and the output files record calls to the unchanged author API. No CORNETO implementation files are copied.
- The `fetch_authors.sh` and `verify_archive.py` helpers are EVIDA-authored wrappers; they do not embed or relicense the upstream solver implementations. This folder makes no separate license grant for those wrappers beyond the publishing repository's applicable terms.
- The four PDE4B/D Boolean formulas, synthetic cost assumptions and next-action labels are new comparison inputs, not claims drawn from a source paper. The native EVIDA JSON files are saved inputs and outputs from the separate current product calculator; this package does not copy that implementation.

For scientific context, the IPF source-prior diagnostic used the GSE47460/GPL14550 whole-lung contrast and inferred TF scores; the public [summary](corneto/real-three-query-summary.json) identifies the source-input hashes and method limits without redistributing the original prior or LP.
