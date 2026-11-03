# CheMeleon fine-tuning 독립 검토

수정 동결본 `338a1e229ab3a848058eb694075159b8802ad3b873beb4949847a773932825ab`에서 추가 학습 중단 사유를 발견하지 않았다. 공식 시험 정답을 열지 않고 30개 입력 분할, 실제 채점기의 합성 사례 16개, 첫 과제의 두 실제 학습 산출물을 독립적으로 확인했다. 검토 자체는 CPU만 사용했고 모델 학습·GPU·네트워크 호출은 0회다.

원본 동결본 `6bf294ade406c2761380a6fa1943e1b9bef1e718a0361900dd0b14348438dcea`와 소스를 `original-freeze/`에 보존했다. 아래 문제는 본 과제의 신경망 학습이 시작되기 전에 root에 보고했고, root가 수정·사유 기록 후 재동결했다. 수정된 사본은 `amended-freeze/`에 보존했다. 제품이나 동결된 실험 파일을 이 검토에서 변경하지 않았다.

| 발견 | 영향과 처리 | 근거 |
|---|---|---|
| P1: Spearman 함수의 `math` import 누락 | 학습을 마친 뒤 점수 기록 단계에서 모든 arm이 `NameError`로 실패할 수 있었다. import 추가 확인. | `missing-math-reproduction.json`, `pretraining-repairs-check.json` |
| P1: Chemprop 기본 로더의 singleton tail 제거 | 공식 시험 193행인 2개 과제가 192개 예측만 만들고, 학습 행이 64로 나눈 나머지 1인 3개 과제도 행을 빠뜨렸다. 네 로더의 `drop_last=False` 확인. | `loader-coverage-reproduction.json`, `input-partition-review.json` |
| P2: GPU 점유 시 잔여 계획 기록 누락 | 자원 중단 뒤 남은 arm의 영수증·완료 원장이 없었다. 수정본은 전체 60개에 `not_started_resource_busy`를 남긴다. | `pretraining-repairs-check.json` |
| 동결 무결성 보강 | 작업 시작 시 protocol receipt 해시를 검사하고, 채점 시 completion protocol 해시를 검사한다. | `amended-freeze/run_comparison.py`, `scoring-gate-review.json` |
| 실행 여부 표시 보강 | 모두 미시작이면 GPU 사용 false, 시도했으나 완료된 fit이 없으면 unknown, 완료된 실제 fit이 확인되면 true로 기록한다. | `scoring-gate-review.json` |

`input-partition-review.json`은 30개 전부 PASS다. 이전 GP 동결 소스의 native training-row 정리와 Murcko scaffold 분할을 다시 적용해 학습·검증 행과 순서를 비교했다. 공식 train/test-features 해시, 30개 학습 행렬·레이블 해시, 후보 ID 유일성·분할 간 분리, 내부 학습/검증 scaffold 분리, 학습/검증과 시험의 canonical 구조 분리를 확인했다. 예측 입력 9,802행에는 ID와 SMILES만 있다. 검토 프로그램은 공식 시험 정답 경로를 여는 동작을 차단한다. 최초 프로토콜에 고정된 입력 해시가 수정 동결본에서도 모두 그대로다.

`scoring-gate-review.json`은 실제 수정 채점기와 실제 `verify()`를 변경 없이 실행한 CPU 합성 사례 16개 결과다. 테스트에서 변경한 것은 파일 루트와 합성 자료뿐이다. 가중치로 표시된 바이트도 해시 확인용 합성 파일이며 모델로 읽거나 실행하지 않았다. 합성 과제 30개·계획 arm 60개·29개 target cluster를 사용했다.

- 정상 사례와 시험 정답 순서를 뒤집은 사례에서 validation-only 선택이 동일했다. 같은 점수일 때 RF가 선택됐다.
- 전체 미시작과 전체 실패 사례에서 60개 분모·실패 원장·기존 RF/GP 후보가 보존됐다. GPU 상태 false/unknown도 구분됐다.
- 계획 1개 누락, 중복 후보 ID, 비유한 예측, 잘못된 protocol, 잘못된 검증 MAE, 다른 초기 head, 예측 행 누락, 예측 해시 오류, completion protocol 오류, source 변경, input 변경의 11개 사례가 모두 합성 정답 파일을 열기 전에 차단됐다.
- 정상 채점의 모든 합성 정답 읽기는 전체 예측 봉인 이후에 일어났다. 실제 시험 정답은 한 번도 열지 않았다.

`first-fit-review.json`은 첫 고정 과제 CHEMBL1862_Ki의 pretrained/random 두 fit 각각 23개 점검과 공통 head 점검 PASS다. 실제 저장된 학습 475행, 검증 158행, 시험 특징 161행을 사용했다. 두 arm의 초기 head 해시는 같고 encoder 초기 해시는 다르다. 저장된 scaler는 학습 레이블만으로 재계산한 값과 일치했다. 독립 SciPy Spearman, 검증 MAE, 학습 평균 기준 MAE, 선택 적격성이 기록과 일치했다. 체크포인트 파일 해시, 로그의 최소 val-loss, 그 체크포인트에서 나온 원단위 검증 예측의 정규화 MSE가 일치했다. 17/6 epoch 종료도 best epoch 뒤 patience 5 규칙과 맞았다. 검토에서 추가 예측이나 학습을 실행하지 않았다.

코드의 정보 흐름은 학습 레이블로 scaler와 모델 학습 → 내부 검증 MSE로 checkpoint 선택 → 내부 검증 MAE와 Spearman으로 모델 선택 → 전체 arm의 예측 봉인 → 공식 시험 정답 평가다. 실제 Chemprop 2.3.1의 validation hook이 output transform을 training mode로 두고, prediction에서 원단위로 되돌리는 경로도 확인했다. 따라서 검증 MSE와 원단위 MAE가 서로 다른 단위로 비교되는 문제는 발견하지 않았다. 예측 봉인 전에 검사하는 scorer 자체가 선택의 training-mean MAE를 별도 재계산하지는 않지만, 고정 worker가 정확히 계산하고 첫 실제 fit에서 독립 재계산도 일치했다. 이 점은 현재 실행을 막는 오류로 판단하지 않았다.

이 실험은 root가 같은 30개 과제의 RF/GP 및 고정 CheMeleon 결과를 이미 본 뒤 설계한 후속 실험이다. 새 외부 검증으로 표현할 수 없다. 현재 검토는 실행 무결성과 분할·선택 경로의 확인이며 CheMeleon이 더 좋다는 과학적 결과가 아니다. 사전학습 PubChem 분자와 평가 분자의 중복은 별도 조사하지 않았으므로, 사전학습에서도 본 적 없는 구조라는 주장도 하지 않는다. 실제 완료/실패/미시작 60개 원장과 각 비교의 paired task/target 수를 유지해 최종 결과를 읽으면 된다.

재검토용 파일은 `check_input_partitions.py`, `check_scoring_gate.py`, `check_first_fit.py`다. 모든 스크립트는 공식 정답을 읽지 않는다. 합성 gate와 freeze 사본은 덮어쓰기 방지를 위해 기존 출력 디렉터리가 있으면 중단한다. 새 검토가 필요하면 기존 산출물을 보존하고 새로운 출력 디렉터리를 사용한다.
