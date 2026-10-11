# 독립 익명 과학 판정 인계

attempt-03의 고정 18개 답변은 모두 과학 판정 PASS다. 사전에 동결한 P1–P6의 세부 기준 54개 적용도 모두 PASS이며, 미완료·판정 불가 답변은 없다. 54개는 독립 표본 수가 아니라 18개 답변에 각 세 기준을 적용한 수다. 이 여섯 개발 사례에서는 과학 성능의 차이를 확인하지 못했다.

| 고정 사례 | 확인한 핵심 구분 | 답변 PASS |
|---|---|---:|
| P1 | 읽은 문헌과 결과를 아직 보지 않은 새 개입을 구별 | 3/3 |
| P2 | 같은 공개 결과에 대한 사후 설명을 새 예측으로 바꾸지 않음 | 3/3 |
| P3 | 알려진 원 연구와 아직 관측하지 않은 새 재현을 구별 | 3/3 |
| P4 | 실제 event 7 사전 기록을 보존하고 event 10 결과와 대조 | 3/3 |
| P5 | 더 오래된 기록이어도 결과 뒤에 작성됐으면 사후 설명으로 유지 | 3/3 |
| P6 | 측정 동일성과 선후관계가 불명확하면 시점을 확정하지 않음 | 3/3 |

판정은 위임받은 에이전트의 독립 수동 검토다. 답변을 읽기 전에 기준 해석을 동결했고, 각 답변을 읽은 뒤 판정과 원문 해시를 순차 봉인했다. prose/JSON 형식은 보이는 부분 블라인드였으나, 작성 경로 이름·매핑·raw prompt·provider artifact·제품 코드 스냅샷은 열지 않았다. 경로의 정체를 추측하거나 점수에 사용하지 않았다. 모든 답변을 읽은 후에도 키는 열지 않았다.

## 별도로 보존한 B09의 모호성

B09/P6는 연결되지 않은 측정의 시점이 불명확하다고 반복해서 밝히고, 사전 예측·선행 기록의 점수를 부여하지 않는다. 다만 p6-assigned에 붙은 prediction/binding 필드에는 `reconstructed_after_result`를 사용하면서, 이는 읽은 문헌 이후 작성한 조건부 설명을 뜻하며 해당 검사의 결과가 이미 관측됐다는 뜻이 아니라고 설명한다.

사전 동결 기준은 명시적인 unresolved-context 경로를 허용하므로 과학 판정은 PASS다. 필드 하나만 읽는 소비자는 시점을 오해할 수 있다는 표현상의 문제는 별도 진단으로 남겼다. 이 검토는 해당 필드의 안전한 후속 처리나 native schema/dispatch의 정확성을 인증하지 않는다. 이 사후 보조 진단을 새로운 주 점수로 섞지 않는다. 상세 문장·JSON pointer는 [B09 판정](<SOURCE>/independent-review/judgments/B09-judgment-01.json)에 보존했다.

## 무결성과 범위

실행 담당자의 키 없는 manifest는 planned 18, terminal 18, returned identity-accepted 18을 확인한다. 이 수는 attempt-03의 고정 답변 분모다. 이전 실행 시도들의 원장은 이 블라인드 검토 범위 밖이며 읽지 않았다. 과거 시도까지 포함한 전체 실행 분모를 18이라고 주장하지 않는다.

독립 검증은 다음을 확인했다.

- 36개 visible-case/answer 파일의 SHA가 실행 담당자의 최종 manifest와 일치한다.
- 모든 수동 초안·판정·보고서 봉인과 사전 기준·공통 자료 해시가 그대로다.
- 99개 판정 인용의 정확한 원문, 원문 행 번호, 해당 JSON pointer가 일치한다.
- 구조형 답변 12개에 있는 공통 과학 자료 인용 225건의 경로·문구가 자료와 일치한다. 이는 보조 문자열 검증으로, 완전한 의미 검증이나 추가 과학 점수가 아니다. prose 형식에는 불이익을 주지 않았다.

공통 과학 자료는 기존 원 연구를 선택해 추출한 20행 packet이다. 전체 원문·원 측정 자료를 새로 검증한 것이 아니다. 추가 시점·기록 이력은 합성 사례 사실이며 실제 nerandomilast 실험의 연혁이 아니다. 여섯 개 선택된 개발 사례와 경로별 단일 응답으로 일반 정확도, 통계적 우위, 임상 타당성 또는 생물학적 발견을 주장할 수 없다. 검토 중 모델 호출·외부 조회·GPU 사용·재학습·제품 수정은 하지 않았다.

## 봉인 자료

- [전체 익명 판정 보고서](<SOURCE>/independent-review/blinded_review_final.md)
- [전체 판정 JSON](<SOURCE>/independent-review/blinded_review_final.json)
- [최종 판정 봉인](<SOURCE>/independent-review/blinded_review_final.seal.json)
- [무결성 검증 receipt](<SOURCE>/independent-review/final-integrity-verification.json)
- [판정 전에 동결한 기준 해석](<SOURCE>/independent-review/criterion-interpretation-01.json)

기준 해석 SHA: `bbec185cb660b34a2943a5b4f698a20677164ab9e08c6508625aaba01744726a`.

최종 판정 seal SHA: `554f5cb13ed77e9ea990e631284407a28bd2081a7c9bf96a72d8fb396fc510e2`.

직접 확인한 blind-file-manifest SHA: `9dccbfad1d2b0fe6856e0ec9870e646edea2884153e2420833145b4bc9e67ebf`.

실행 담당자가 전달한 전체 output-seal SHA: `0cf43599cad98beb0e2c34680fbebbbb7b1c6ea455320b25a2a17bb7070f3395`. 이 전체 seal의 내용은 허용된 블라인드 입력 범위 밖이므로 열지 않았으며, 직접 확인한 것으로 표현하지 않는다.

Root가 이후 키를 열어 고정 여섯 사례의 경로별 집계를 별도 파일로 만들 수 있다. 원 판정과 봉인은 그대로 유지한다. 같은 시점 판정 검증을 추가 호출로 반복하지 않고, 다음 관측을 선택하는 데 실제로 도움이 되는지 평가하는 후속 작업으로 넘어간다.
