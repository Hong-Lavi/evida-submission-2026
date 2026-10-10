# 익명 과학 판정

고정된 18개 분모 중 11개 답변을 판정·봉인했고, 7개가 미완료다. 답변 작성 경로의 이름과 매핑은 열지 않았다. 아래 결과는 선택된 합성 시점 사례에 대한 수동 과학 판정이며, 일반 정확도나 생물학적 검증 결과가 아니다.

형식과 답변 길이는 과학 점수에 반영하지 않았다. native schema/dispatch 검증은 이 검토 범위 밖이다. 각 판정의 인용은 원 answer.txt의 정확한 문자열 및 JSON pointer/행 위치로 확인했으며, 원본과 판정 해시를 함께 보존했다.

| 익명 ID | 사례 | 과학 판정 | 판정 파일 |
|---|---|---|---|
| B01 | P2 | pass | [B01](<SOURCE>/independent-review/judgments/B01-judgment-01.json) |
| B02 | P4 | pass | [B02](<SOURCE>/independent-review/judgments/B02-judgment-01.json) |
| B03 | P5 | pass | [B03](<SOURCE>/independent-review/judgments/B03-judgment-01.json) |
| B04 | P1 | pass | [B04](<SOURCE>/independent-review/judgments/B04-judgment-01.json) |
| B05 | P1 | pass | [B05](<SOURCE>/independent-review/judgments/B05-judgment-01.json) |
| B06 | P3 | pass | [B06](<SOURCE>/independent-review/judgments/B06-judgment-01.json) |
| B07 | P4 | pass | [B07](<SOURCE>/independent-review/judgments/B07-judgment-01.json) |
| B08 | P3 | pass | [B08](<SOURCE>/independent-review/judgments/B08-judgment-01.json) |
| B09 | P6 | pass | [B09](<SOURCE>/independent-review/judgments/B09-judgment-01.json) |
| B10 | P3 | pass | [B10](<SOURCE>/independent-review/judgments/B10-judgment-01.json) |
| B11 | P5 | pass | [B11](<SOURCE>/independent-review/judgments/B11-judgment-01.json) |
| B12 | 미확인 | 미완료 | — |
| B13 | 미확인 | 미완료 | — |
| B14 | 미확인 | 미완료 | — |
| B15 | 미확인 | 미완료 | — |
| B16 | 미확인 | 미완료 | — |
| B17 | 미확인 | 미완료 | — |
| B18 | 미확인 | 미완료 | — |

## B01 — P2_same_result_already_seen

p2-assigned is explicitly identified as the local alias of mkp1-known; event 10 is the already seen same result.

reconstructed_after_result (equivalent explicit retrospective prose)

- P2.1: **pass**. Identifies event-10 disclosure before any prediction and explicitly denies prospective credit for the current explanations.
  - `line 1`: “Consequently, explanations formulated now are retrospective; they cannot be credited as successful prospective predictions or as new experimental observations.”
- P2.2: **pass**. Keeps local alias and measurement identity fixed and explicitly rejects chronology laundering by renaming.
  - `line 1`: “Renaming the check does not change that chronology.”
  - `line 15`: “No such experiment was performed here, and it would not alter the retrospective status of p2-assigned.”
- P2.3: **pass**. Treats downstream loss as compatible with hA, not uniquely discriminating hA from hB; names alternative explanations and missing intervention/readout controls.
  - `line 5`: “Thus the known loss is compatible with hA but does not uniquely distinguish hA from hB.”
  - `line 13`: “For the assigned measurement, the exact downstream endpoint, perturbation identity and direction, efficacy, drug dose, assay schedule, sample size and control results are unspecified.”

모호한 점: Suggested future controls are a proposed separate experiment, not claimed completed. The mediator-control D1-D4 assay is outside this score.

[원 답변](<SOURCE>/attempt-03/blind-review/B01/answer.txt) · answer SHA `4153d6cb46d5acb87be4e86799993a09f2894f1a3ea741d0bd8c47872d7d65ee`

## B02 — P4_actual_prior_prediction_record

p4-assigned/prior-check and P4_actual_prior_prediction_record-instance are explicitly kept identical.

actual previously recorded prospective prediction at event 7; current assessment after event-10 disclosure

- P4.1: **pass**. Uses the actual fixture artifact and event order, not a literature citation as proof of earlier prediction.
  - `line 13`: “The preserved artifact is prior_prediction_P4, recorded at scenario event 7, with measurement_instance 'P4_actual_prior_prediction_record-instance'.”
  - `line 15`: “The history reveals outcome_index 0 at event 10 and places the current review at event 12. Thus, the original forecasts precede disclosure within the stipulated chronology.”
- P4.2: **pass**. Preserves original hA [0], hB [1], complete coverage, prospective origin and fixture assumption/rationale.
  - `line 13`: “Its unchanged declarations are hA: outcome_indices [0], and hB: outcome_indices [1]. Both have coverage 'complete', origin 'prospective', an empty alternative_id, the assumption 'Explicit synthetic prior declaration, not a paper result', and the rationale 'Unchanged earlier expectation under the scenario conditions.'”
- P4.3: **pass**. Assesses the preserved forecast against outcome 0, refuses to expand hB after seeing it, and distinguishes forecast mismatch from refuting broad coexisting mechanisms.
  - `line 15`: “The earlier hB set must not be expanded after seeing the result.”
  - `line 15`: “Equally, this conditional forecast mismatch does not globally falsify the broader, nonexclusive hB statement in the reference loop.”

모호한 점: Condition wording in the fixture is generic; the answer correctly declines to invent intervention dose, endpoint, effect size or confidence interval.

[원 답변](<SOURCE>/attempt-03/blind-review/B02/answer.txt) · answer SHA `a9a9c142a5c85637debd9d537d5235c1639437328a5bdbda62247b007c91e52d`

## B03 — P5_earlier_hindsight_record

p5-assigned/P5_earlier_hindsight_record-instance; outcome 0 at event 5, record at event 7, review at event 12.

reconstructed_after_result retained in observations and bindings

- P5.1: **pass**. Explicitly retains hindsight origin despite the artifact predating the current response.
  - `/hypothesis_review/scope/checks/0/reason`: “P5_earlier_hindsight_record-instance의 outcome 0은 event 5에 알려졌고 prior_prediction_P5는 event 7에 처음 작성되었다. event 12에 이 기록을 재사용해도 결과 이전 예측이 되지 않는다.”
- P5.2: **pass**. Explicitly refuses to turn older storage into previously-recorded/prospective evidence; says the agreement is hindsight fit, not predictive or independent validation.
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “event 12 이전에 저장됐다는 이유로 previously_recorded 또는 prospective로 바꾸지 않는다.”
  - `/judgment_context/observation_reviews/4/explanatory_adequacy`: “알려진 결과와 사후 기대의 일치다. 예측력·독립 검증·MKP1 필요성을 입증하지 않는다.”
- P5.3: **pass**. Preserves the original [0]/[1] outcome declarations and reconstructed origin, links the actual prior artifact, and refuses to rewrite hB as [0,1].
  - `/judgment_context/observation_reviews/5/processing_validity`: “원 [1]·complete·reconstructed_after_result를 보존한다. 알려진 outcome 0에 맞추어 원 선언을 [0,1]로 고쳐 쓰지 않는다.”

모호한 점: The structured outcome interpretation uses insufficient_precision, but explicitly explains this as missing quantitative information rather than a known failed measurement or denial of the stipulated outcome. It does not alter the chronology judgment.

[원 답변](<SOURCE>/attempt-03/blind-review/B03/answer.txt) · answer SHA `f3f784548b70d3f1a4382b33e4c63ef86f6ddc3224e693f0ee9f5ff61b517dfe`

## B04 — P1_new_intervention_after_literature

p1-assigned/mkp1-new is distinguished from known published assays and remains an unmeasured perturbation/control/rescue check.

prospective for the assigned new intervention; known literature remains background interpretation

- P1.1: **pass**. Explicitly grounds prospective origin in absence of this intervention's outcome, despite prior literature exposure.
  - `/hypothesis_review/observations/0/predictions/0/rationale`: “문헌 결과는 이미 알려져 있지만 이 개입 결과는 아직 없으므로 이번 구체 예측의 origin은 prospective이다.”
- P1.2: **pass**. Separates published measurements from the new check and does not present literature as a prior forecast for it. Retrospective meaning is conveyed by the explicit known-literature/new-unseen contrast rather than an obligatory enum.
  - `/hypothesis_review/causal_steps/0/target_context`: “문헌의 인간 IPF 폐 섬유아세포 관측과 계획된 p1-assigned(mkp1-new)는 별개이며, 새 확인의 실제 시료·판독·시점은 아직 정해져 있지 않다.”
  - `/hypothesis_review/causal_steps/1/evidence_groups/1/applicability_rationale`: “이 저자 가설은 새 mkp1-new 확인에 대한 사전 예측 기록이 아니다.”
- P1.3: **pass**. Leaves mediator causality unestablished and recognizes that broad hA/hB outcome sets overlap rather than claiming completed discrimination.
  - `/hypothesis_review/causal_steps/0/evidence_groups/0/causal_support_rationale`: “약물 처치 뒤의 두 반응으로 매개자의 필요성·충분성을 정할 수 없다.”
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “양 가설의 호환 결과가 겹치므로 결과 번호만으로 승자를 정할 수 없다.”

모호한 점: Outcome interpretations say adequate_measurement, but the answer explicitly makes these conditional on future validity and precision checks; no existing result is declared adequate.

[원 답변](<SOURCE>/attempt-03/blind-review/B04/answer.txt) · answer SHA `1c562de8e35f7056922ad79410278c9e5a5b7f8742a673defd75ad473f070f55`

## B05 — P1_new_intervention_after_literature

p1-assigned is explicitly the alias of the unseen mkp1-new intervention.

prospective for new intervention predictions, separately from already observed publication results

- P1.1: **pass**. Both observation predictions and bindings are prospective for the same specified new measurement; rationale says it is being written before any result.
  - `/hypothesis_review/observations/0/predictions/0/rationale`: “이 예상은 결과 미관측 상태에서 지금 작성한 prospective이며, source_packet은 문헌 배경일 뿐 과거 예측 기록이 아니다.”
- P1.2: **pass**. Explicitly denies that current predictions preceded the original paper observations, preserving original-versus-new chronology.
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “이 조건부 예상은 새 개입 결과 전에 작성한 prospective이며, 원 논문의 관측을 사전 예측했던 것으로 표시하지 않는다.”
- P1.3: **pass**. States that MKP1 contribution is unproved and that overlapping possible outcomes do not select an exclusive mechanism.
  - `/hypothesis_review/scope/hypotheses/0/reason`: “약물 반응은 있지만 MKP1 매개 기여는 입증되지 않아 참조 루프의 proposed 상태를 강화할 근거가 없다.”
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “두 결과 모두 겹칠 수 있어 이 검사만으로 배타적 기전을 선택할 수 없다.”

모호한 점: The word retrospective is not required: the explicit statement that the original observations were not predicted in advance supplies the expected distinction.

[원 답변](<SOURCE>/attempt-03/blind-review/B05/answer.txt) · answer SHA `40c3e19c276286f15677c26c5dcdafd54b06ecf396f76c95b3b63ee865714244`

## B06 — P3_new_replication_after_original_study

p3-assigned/replicate-new is a separately identified uncollected matched-donor replication, not the original assays.

prospective replication expectations informed by known original findings

- P3.1: **pass**. Explicitly allows prospective replication forecasts while its measurements remain unseen and recommends recording them before collection.
  - `line 16`: “The expectations below are formulated with the published results already known, while the replication measurements remain uncollected and unrevealed. They can guide a prospective replication assessment, but cannot be presented as predictions made before the original findings.”
  - `line 32`: “The next useful step is to finalize the replicate-new protocol and record these expectations before obtaining its measurements.”
- P3.2: **pass**. Treats original results as known background and denies that they are the new replication outcome or a forecast predating the original results.
  - `line 1`: “Published results therefore provide its evidential background, not its outcome.”
  - `line 16`: “The authors’ reported competition hypothesis belongs to the published study and must remain separate from a forecast for this replication.”
- P3.3: **pass**. Frames successful replication as reproducibility under specified conditions, not causal proof or independent mechanism discovery; both broad explanations remain compatible.
  - `line 22`: “Because hA and hB can both hold, replication of the published panel alone cannot distinguish them.”
  - `line 26`: “If Outcome 1 occurs under those definitions, it supports reproducibility of the specified response in the replication conditions, while remaining compatible with both hypotheses.”
  - `line 26`: “Without a mediator intervention, it does not selectively refute hA or establish hB. Neither outcome should be entered as observed now.”

모호한 점: The generic lost/retained outcome labels need endpoint-specific definitions; the answer explicitly identifies this and retains mixed/inconclusive possibilities without asserting an observed replication result.

[원 답변](<SOURCE>/attempt-03/blind-review/B06/answer.txt) · answer SHA `a8e469cd500136d3313795d79c628efe467a0e9206c2673bd046282c2fa019f3`

## B07 — P4_actual_prior_prediction_record

p4-assigned/prior-check and the exact P4 fixture measurement remain fixed.

previously_recorded, explicitly preserving original prospective origin at event 7 before outcome event 10

- P4.1: **pass**. Cites the actual prior fixture and correct event order for the same instance.
  - `/hypothesis_review/observations/0/validity_requirements/0`: “prior-check는 p4-assigned의 별칭이며 동일한 P4_actual_prior_prediction_record-instance를 가리킨다. prior_prediction_P4는 사건 7에 기록·공개되었고, 결과 0은 사건 10에 공개되었으며 현재 검토는 사건 12이다.”
- P4.2: **pass**. Preserves the original hA [0], hB [1], complete coverage and prospective origins while explaining that current reuse is previously_recorded.
  - `/hypothesis_review/observations/0/predictions/0/rationale`: “prior_prediction_P4의 사건 7 기록은 outcome_indices=[0], coverage=complete, origin=prospective이며 원 rationale은 Unchanged earlier expectation under the scenario conditions.이다.”
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “prior_prediction_P4의 사건 7 기록은 outcome_indices=[1], coverage=complete, origin=prospective이며 원 rationale은 Unchanged earlier expectation under the scenario conditions.이다.”
- P4.3: **pass**. Explicitly refuses to broaden the hB prediction after seeing outcome 0 and keeps broad biological coexistence distinct from the fixed narrow forecast.
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “결과를 본 뒤 [0,1]로 넓히지 않는다. 다만 광범위한 병렬·공존 기여 자체는 이 좁은 예측과 동일하지 않아 전면 기각되지 않는다.”

모호한 점: adequate_measurement is explicitly a conditional interpretation, not proof that the scenario supplied real measurement quality evidence.

[원 답변](<SOURCE>/attempt-03/blind-review/B07/answer.txt) · answer SHA `05f12df5a605013717c81fcbe2ba7ace2388bcd25b64840012636bfdef25ab3d`

## B08 — P3_new_replication_after_original_study

p3-assigned/replicate-new is expressly uncollected and separate from published SMAD3/co-IP/CUT&RUN assays.

prospective for new replication, reconstructed_after_result for known original contexts

- P3.1: **pass**. Uses the positive scenario statement that the new measurements are unobserved to justify prospective expectations, rather than absence of records.
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “Chronology is prospective for replicate-new on the supplied visible facts; no earlier measurement-specific prediction is supplied.”
  - `/judgment_context/unresolved_context/2`: “this positive statement, not the absence of outcome links, supports prospective origin.”
- P3.2: **pass**. Explicitly distinguishes current reconstruction of known original results from forecasts for a different new replication, with separate context bindings.
  - `/judgment_context/unresolved_context/3`: “Current reconstructions of known published results remain reconstructed_after_result; literature-informed expectations for the distinct new replication remain prospective.”
- P3.3: **pass**. Treats the drug-only replication as reproducibility assessment; overlapping hypotheses prevent a causal winner, and a separate intervention would be required.
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “The overlap with hA prevents mechanistic discrimination by this drug-only replication alone.”
  - `/judgment_context/observation_reviews/2/next_check`: “This tests reproducibility. A later selective mediator perturbation is needed to test causal contribution; no new experiment has been performed here.”

모호한 점: Proposed acute replication conditions are identified as proposals and unspecified details remain open. No source-like future pattern is entered as already observed.

[원 답변](<SOURCE>/attempt-03/blind-review/B08/answer.txt) · answer SHA `7ab0ed3867508216743d51d59e5fafa25c684f62c38d786649b8ea85f7325570`

## B09 — P6_unresolved_timing_no_prior_record

p6-assigned identity, actual execution and connection to the reported assay remain unresolved.

Explicitly unresolved for the assigned measurement; reconstructed_after_result labels are explained as current conditional reasoning after reading literature, not evidence the assigned outcome was known.

- P6.1: **pass**. The fixed rubric permits an explicit unresolved-context route. The answer expressly leaves the assigned result identity and prediction ordering unknown and denies that its retrospective field proves an observed assigned outcome.
  - `/judgment_context/unresolved_context/0`: “지정 검사와의 연결 및 예측의 선후관계는 확정할 수 없다. 현재의 reconstructed_after_result 표기는 제공된 문헌 보고를 읽은 뒤 작성한 조건부 기대를 표시하며, p6-assigned 결과가 이미 관측됐다는 주장이 아니다.”
  - `/judgment_context/contexts/3/time`: “예측 작성, 결과 접근, assay 실행 및 분석 시점 모두 미확인”
- P6.2: **pass**. Invents neither a prior artifact nor timing. Explicitly treats the researcher's possible earlier prediction as unverified and requests its preserved record.
  - `/judgment_context/assumptions/1/statement`: “연구자는 예측이 있었을 수 있다고 보고했지만 그 원문을 제공하지 않았다. case.history=[]이다. 이는 과거 예측이 없었다는 증거도, 있었다는 확인도 아니다.”
- P6.3: **pass**. Missing execution linkage leads to unknown execution/outcome status, not a conclusion of unseen results or prospective eligibility.
  - `/judgment_context/assumptions/0/statement`: “반응 보고와 p6-assigned 사이의 실행 연결은 제공되지 않았다. 따라서 실행 여부나 실제 outcome을 확정할 수 없다.”
  - `/judgment_context/observation_reviews/3/explanatory_adequacy`: “기여 가설을 실제 결과와 대조하거나 사전 예측 적중으로 평가할 수 없다.”

모호한 점: Material representation caveat: reconstructed_after_result appears on predictions and bindings attached to p6-assigned even though its actual chronology is unresolved. A consumer reading only that field could misread it. The scientific primary result passes because the rubric explicitly permits unresolved-context reasoning, the answer repeatedly states the assigned chronology is unknown, and it grants neither prospective nor unsupported prior-record credit. This caveat is retained separately and is not treated as proven native schema or dispatch correctness.

[원 답변](<SOURCE>/attempt-03/blind-review/B09/answer.txt) · answer SHA `a64e50c99d7e5536064a450c397b1ee3f6beed853b0a0b2b7067fe0b9ff799d7`

## B10 — P3_new_replication_after_original_study

p3-assigned is replicate-new; published original assays and the uncollected matched-donor replication have separate contexts.

prospective for replicate-new and reconstructed_after_result for known original observations

- P3.1: **pass**. Explicitly grounds prospective forecasts in the new measurement being unseen and rejects automatic hindsight classification from reading the paper.
  - `/hypothesis_review/scope/checks/0/reason`: “replicate-new의 미측정 결과에 대한 기대를 지금 작성하므로 prospective이다. 출판 결과를 알고 있다는 사실이 별도 새 인스턴스의 예측을 소급 예측으로 바꾸지는 않는다.”
- P3.2: **pass**. Keeps known original observations and unknown replication separate in the scientific discussion and in context bindings.
  - `/judgment_context/unresolved_context/2`: “기존 관측을 사용한 현재 해석은 reconstructed_after_result, 미수집 replicate-new의 현재 기대는 prospective로 분리했다.”
  - `/hypothesis_review/observations/0/validity_requirements/0`: “p3-assigned의 측정 인스턴스는 replicate-new이다. 새 측정은 수집·공개되지 않았다. 출판 결과는 이미 알려진 별도 관측이다.”
- P3.3: **pass**. Calls the proposed replication a reproducibility check rather than causal discrimination, and retains the need for a separate selective intervention.
  - `/judgment_context/observation_reviews/4/next_check`: “이 복제는 재현성 확인이며, hA와 hB를 가르려면 이후 선택적인 MKP1 교란 비교가 필요하다.”
  - `/judgment_context/unresolved_context/4`: “두 가설은 넓고 공존 가능하므로 복제의 유지·감소만으로 배타적인 인과 선택을 할 수 없다.”

모호한 점: CDKN1A occupancy is recommended as a primary readout, with an explicit statement that this is a present design proposal rather than a historical or already fixed specification. This does not change original-versus-replication chronology.

[원 답변](<SOURCE>/attempt-03/blind-review/B10/answer.txt) · answer SHA `d9ea3f755690aa4bbafa137ce5d7bac48271308039282eeaa3c28538ad17005c`

## B11 — P5_earlier_hindsight_record

p5-assigned/P5_earlier_hindsight_record-instance remains the same event-5 outcome, event-7 explanation and event-12 review.

reconstructed_after_result preserved for the older artifact and current reuse

- P5.1: **pass**. Correctly orders known outcome before first explanation and keeps its hindsight origin despite later reuse.
  - `/hypothesis_review/scope/checks/0/reason`: “P5_earlier_hindsight_record-instance의 결과 0은 event 5에 알려졌고, prior_prediction_P5는 event 7에 처음 작성됐다. event 12에 그 기록이 존재해도 두 예상의 origin은 reconstructed_after_result로 유지한다.”
- P5.2: **pass**. Explicitly denies promotion to prospective status and distinguishes an older document from a prediction predating its result.
  - `/hypothesis_review/scope/checks/0/reason`: “previously_recorded나 prospective로 승격할 수 없으며, 새로운 측정이나 독립적인 예측 성공도 아니다.”
  - `/judgment_context/observation_reviews/5/applicability`: “이름의 prior나 과거 파일의 존재는 결과 이전 예측의 증거가 아니다.”
- P5.3: **pass**. Keeps actual artifact, hA [0], hB [1], original rationale, coverage and reconstructed origin. Does not change the earlier mismatch into a prospective failure.
  - `/hypothesis_review/observations/0/predictions/0/rationale`: “원 기록의 문장 Unchanged earlier expectation under the scenario conditions.와 결과 목록 [0], coverage complete를 보존한다.”
  - `/hypothesis_review/observations/0/predictions/1/rationale`: “원 기록의 문장 Unchanged earlier expectation under the scenario conditions.와 결과 목록 [1], coverage complete를 보존한다.”
  - `/judgment_context/observation_reviews/6/processing_validity`: “과거 예상과의 차이를 숨기지 않되, 사후 기록을 사전 예측 실패로 재분류하지 않는다.”

모호한 점: insufficient_precision is explicitly missing information about discriminability, not a claim the stipulated known outcome is invalid. Chronology itself is correctly said to be known.

[원 답변](<SOURCE>/attempt-03/blind-review/B11/answer.txt) · answer SHA `4ee7e50da623c3351e13dfee520c3d2cef100024634a57649856e46494f5db22`
