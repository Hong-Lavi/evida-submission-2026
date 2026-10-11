# Mechanism methods: choosing the next informative check

For four explicitly assumed PDE4B/PDE4D explanations, [caspo](https://github.com/bioasp/caspo/tree/45b41124ab933996687f1e0581a4f15b32e7806f) and current EVIDA both selected **B-only and D-only perturbations**. When all four explanations led to the same next research action, EVIDA selected **zero further checks**. It also retained all four when perturbation success failed or readout precision was insufficient.

This is a formal model-specification pilot, not a PDE4 biological finding. The result supports using action changes and measurement validity to decide whether another mechanistic check is worthwhile.

| Saved comparison | Input and result |
|---|---|
| Author Toy `learn → classify → design` | Five learned networks, three I/O behaviors, one optimal design; [Toy inputs and outputs](caspo/toy/) |
| Four assumed models, three allowed perturbations | B-only, D-only, AND, OR/coexistence models produced four behaviors. Author design selected the two single perturbations; each separates four of six pairs, together all six. Joint perturbation separates zero in this stipulated set. [Inputs and outputs](caspo/four-model/) |
| Current EVIDA selector, four native calls | Distinct actions: same B/D plan. Shared action: stop with zero. Failed intervention: hold. Insufficient precision: hold. [Exact four input/output pairs](caspo/native-comparison/) |

`B` and `D` mean effective binary signals *after verified selective perturbation* and `Y` is an assumed binary readout in one matched setting. `B=0,D=1` denotes B-only suppression; `B=1,D=0` D-only suppression; `B=0,D=0` joint suppression. The four formulas are `Y=B`, `Y=D`, `Y=B∧D`, and `Y=B∨D`. No TF score was converted into Boolean activity. Under these formulas, a D effect does not disprove B: the coexisting OR explanation remains until a B-sensitive observation separates it. Equal synthetic costs and a budget of three units were stipulated for the native comparison; these are not experimental quotes. [The independent tables](caspo/four-model/verification/independent-check.json) and [cross-method archive checker](verify_archive.py) check the saved outputs.

Caspo's original design maximizes distinctions across **model pairs** and does not receive next-action labels. Its saved two-perturbation design therefore remains the applicable author result when the four actions are relabeled as one; no second caspo solve was made for that relabeling. The current EVIDA selector uses action adequacy, cost/budget and result-validity gates. This comparison supports retaining its action-aware F3 choice and considering caspo only as a conditional source of explicitly justified behavior classes. It does not support replacing F2 learning from current TF statistics.

A separate [CORNETO](https://github.com/saezlab/corneto/tree/d9f6d238d6c41cc20ecc0b4a17d105cbf209b360) method trial tested two small, declared synthetic controls and one existing IPF source-prior diagnostic:

- In a six-edge synthetic branch control, unmodified `CarnivalILP` fit both stipulated TF signs with error 0 and native objective 0.8. Setting A to zero retained a B-branch solution with the same fit and objective. [Frozen input](corneto/synthetic/inputs/frozen-input.json) and [two author-result JSONs](corneto/synthetic/outputs/).
- A four-edge forced co-parent control found `CarnivalFlow` with exclusive paths and `CarnivalILP` infeasible when both same-sign parents were required. Turning Flow exclusivity off produced `T=2` and a negative measurement-error term, which cannot be read as a bounded −1/0/+1 state fit. [Exact synthetic specification](corneto/synthetic/inputs/forced-co-parent.json) and [saved outputs](corneto/synthetic/outputs/).
- For **one** matched IPF input, three `CarnivalILP` queries—base, GSK3B=0, and MDM2=0—were optimal with E2F4 positive and IRF1 negative, weighted sign error 0, and native objective 1.4 each. This shows alternative same-fit solutions within that specified prior, not exhaustive alternatives or a new biological validation. [Three-query summary](corneto/real-three-query-summary.json) records input hashes, settings and timings. The 3,520-edge original prior and mapping are outside this public package, so replaying these real queries requires the matching private inputs and official author API. The public summary is not a stand-in for those inputs.

CORNETO's raw selected edge may point to a node with inactive state; exporting every selected edge as an active mechanism would overstate the author solution. The small co-parent control also shows a representation limit. On the present evidence, EVIDA retains its CARNIVAL method for this role. CORNETO's native objective 1.4 is not compared numerically with the existing CARNIVAL objective 1.2.

The denominator is [recorded separately](corneto/execution-accounting.json): **14 actual CORNETO solver invocations total**, of which three are the same real input's three queries; the synthetic controls and recording failures are separate. The saved-result verifier's 114 assertions are checks, not cases. No new solver, LLM or GPU call was made to assemble this package.

## Reproduce and check

`python3 verify_archive.py` checks all packaged SHA256 values, row counts, author-result correspondence and the four native outcomes without invoking a solver. `bash -n fetch_authors.sh` and the archive verifier's AST parse check syntax only. These local checks were run on the assembled package. [MANIFEST.json](MANIFEST.json) separates original private result hashes from public-file hashes.

For an independent author run, `bash fetch_authors.sh ./new-author-sources` obtains both official checkouts at their pinned commits (network access required; this fetch script was syntax-checked but not run while packaging). Install the pinned [caspo checkout](https://github.com/bioasp/caspo/tree/45b41124ab933996687f1e0581a4f15b32e7806f) and its documented Python/clingo dependencies in a separate environment. From this package directory, run the following into a **new** replay directory so archived results remain intact:

```bash
mkdir -p replay
caspo --out replay/toy test --fatal --testcase Toy --threads 4
caspo --out replay/classify classify caspo/four-model/inputs/networks.csv caspo/four-model/inputs/setup.json --threads 4
caspo --out replay/design design replay/classify/behaviors.csv caspo/four-model/inputs/setup.json --list caspo/four-model/inputs/candidates.csv --nexp 3 --threads 4
```

The native EVIDA input pairs call `select(problem, result=result, calculation_version="2")` from `evida/next_observation.py` matching the SHA256 in [native-receipt.json](caspo/native-comparison/native-receipt.json). These author/native reruns were not performed while packaging and can differ in timing.

For CORNETO's synthetic controls, use the pinned [author commit](https://github.com/saezlab/corneto/tree/d9f6d238d6c41cc20ecc0b4a17d105cbf209b360), its `CarnivalILP`/`CarnivalFlow` APIs, HiGHS, and the saved synthetic inputs. The exact settings and expected statuses are above and in the result JSONs. The real three-query summary records enough to identify the original input but cannot reproduce that run from public files alone. See [NOTICE.md](NOTICE.md) for source and license terms.
