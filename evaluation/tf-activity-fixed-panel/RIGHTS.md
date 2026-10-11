# Source attribution and package contents

Checked against the official source pages on **2026-10-11**. This package distributes EVIDA-authored experiment scripts, numerical outputs, hashes, validation records and 30 minimal factual task locators. The original prior databases, full KnockTF CSVs, author package implementations and R runtime are obtained separately.

| Source | Official terms and package treatment |
|---|---|
| [DoRothEA](https://saezlab.github.io/dorothea/) | The License section specifies academic use and points to a separate version for non-academic use. The frozen interaction table is external; this package provides its SHA256 and numerical results. |
| [CollecTRI](https://raw.githubusercontent.com/saezlab/CollecTRI/main/README.md) | The authors describe CollecTRI as freely available with use subject to the original resource licenses. This package carries the computed scores and the frozen table's SHA256; the interaction table remains external. |
| [OmniPath FAQ](https://omnipathdb.org/#faq) | Users must comply with the licenses of the constituent resources. Obtain the relevant prior resources under their applicable terms. |
| [decoupleR](https://saezlab.github.io/decoupleR/) | The official methods guidance permits academic and commercial use except for VIPER. This experiment invokes ULM, MLM and raw WMEAN. The installed decoupleR 2.12.0 DESCRIPTION declares `GPL-3 + file LICENSE`; obtain the implementation under its package terms. EVIDA's included wrapper calls these author functions. |
| [KnockTF benchmark files on Zenodo](https://zenodo.org/records/7035528) | The inspected record HTML rendered an empty License field. Full CSVs remain external, with official locators and exact hashes in `SOURCE_DATA.md`. |

The numerical outputs include TF activity scores, ranks and TF-own-expression baseline values computed for the fixed experiment. The 30 factual locators contain task identifiers, target names, profile identifiers and perturbation labels. Original interaction edges and the full expression matrix remain with their sources. Source terms apply when obtaining and using those external inputs.

EVIDA-authored scripts are included with the researcher's explicit publication authorization. The public repository has no separate root LICENSE file; no additional license is assigned here.
