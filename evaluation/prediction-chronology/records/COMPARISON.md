# Prediction chronology: fixed component comparison

Astra and both EVIDA variants met all six selected chronology cases. Each answer was judged before the arm map was opened. Explicit chronology guidance is retained as a clarification; the next comparison tests useful actions after an observation.

| Arm | Cases passed | Criteria passed |
|---|---:|---:|
| plain_astra | 6/6 | 18/18 |
| frozen_f1_02 | 6/6 | 18/18 |
| chronology_corrected | 6/6 | 18/18 |

The 18 actual calls returned Astra, with no provider retry. Twelve structured outputs passed the native schema and six were prose. The two earlier setup attempts and their original errors remain separately recorded.

B09 in frozen_f1_02 illustrates a machine-readable ambiguity: a retrospective origin field accompanies an explicit unresolved-timing explanation. The frozen rubric accepts that unresolved route, so its primary pass stays unchanged. The corrected response left the assigned prediction list empty and recorded the unresolved check explicitly.

The six cases cover a new intervention after reading literature, the same known outcome, a new replication, an actual prior prediction, an older hindsight explanation, and unresolved timing. These are synthetic chronology cases on a shared scientific packet. A next-action comparison under valid, failed and unavailable observations will decide whether a further scientific behavior change is useful.

All judgments, exact quotes, source anchors, frozen inputs and output hashes are linked from `EXECUTION_HANDOFF.md` and `independent-review/HANDOFF.md`.
