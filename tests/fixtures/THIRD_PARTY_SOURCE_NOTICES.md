# Source-specific fixture provenance

The fixtures in this directory have different origins. A file called a fixture is
not automatically synthetic or a new scientific measurement.

- `lens/` and `gtopdb/` JSON files are authored synthetic software test inputs,
  described in `SYNTHETIC_SERVICE_FIXTURES.md`.
- `protonation-source.json` is a public projection of five exact ChEMBL
  identifier/SMILES pairs. Its original source hash and its projection hash are
  distinct; source attribution and upstream license are embedded in the projection.
  ChEMBL, EMBL-EBI states that its data are available under CC BY-SA 3.0 Unported:
  https://chembl.gitbook.io/chembl-interface-documentation/about
  https://creativecommons.org/licenses/by-sa/3.0/
- The retained `generated_proposals_20261002.json` and
  `guided_proposals_20261002.json` include historical software-generated structures
  and small projections of retrieved parent structures/source records. Generated
  proposals have no measured activity by virtue of being generated. Retrieved
  ChEMBL/BindingDB records retain their source-specific terms; they are not
  relicensed as project-authored code. BindingDB describes staff-curated data
  licensing on its official information page, and distinguishes other source data:
  https://bindingdb.org/rwd/bind/info.jsp
  Do not assume every imported record has one common curator/license. Exact
  per-record curation/redistribution status is not certified by these tests.
- `protonation-author-reference.json`, `gypsum-butane-software-output.json`, and
  `computation_result_shapes191.json` preserve historical local software outputs.
  A public projection may alias filesystem paths while retaining the original
  source hash separately. This is not a new run or an alteration of measured data.
- Saved workspace/model fragments and screenshots are development showcase
  artifacts and UI regression inputs, not newly executed experiments or blinded
  benchmark reference answers. They do not certify scientific validity.

Original source files and receipts are preserved privately. Public tests use only
the supplied snapshots/projections; a source locator/hash does not redistribute
the located article or grant additional rights to it. Follow the upstream source
terms for further reuse. This notice does not assign a license to third-party data.
