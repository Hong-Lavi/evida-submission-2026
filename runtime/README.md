# 공개 모델 경로와 검토용 런타임 소스

EVIDA 제품은 연구 목표·근거·도구 계약을 입력으로 받고, 모델이 선택한 등록 함수나 판단을 제품의 원래 계약으로 검사해 실행합니다. 구독 경로는 고정된 원입력 색인과 작은 JSON 행동 봉투를 사용하며, 실제 과학 도구 실행·출처·판단은 제품에 남습니다.

## 공개 경로

| 경로 | 모델 · effort | 선택 |
|---|---|---|
| 대회 API 기본 | GPT-6 Sol · medium | 기본 경로 |
| `subscription:claude-opus-5` | Claude Opus 5 · medium | 안내·주의 확인 후 사용자가 직접 선택 |
| `subscription:gpt-6-sol` | GPT-6 Sol · medium | 안내·주의 확인 후 사용자가 직접 선택 |

대회 API의 HTTP403은 화면에 표시하고 다른 제공자로 자동 전환하지 않습니다. API key는 제품 프로세스 메모리로만 전달합니다. 구독 CLI에 전달하는 환경·입력·로그에는 넣지 않습니다. 실제 모델 identity는 응답 검증과 영수증에 남습니다. 경로별 허용량과 영속 호출 ledger는 운영자가 검토한 설정으로 집행합니다.

## 포함한 코드

정확한 파일 SHA256은 [`RUNTIME_SOURCE_MANIFEST.json`](../RUNTIME_SOURCE_MANIFEST.json)에 있습니다.

| 파일 | 역할 |
|---|---|
| `route_transport.py` | 사용자가 선택한 Claude·ChatGPT 구독 경로와 실제 응답 identity 검사 |
| `transport_contract.py` | 입력·도구 결과의 무손실 색인, 등록 함수·최종 판단 계약 검증 |
| `product_indexed_input82.py` | 선택한 원입력 범위를 읽기 위한 색인과 주소 |
| `optional_array_normalization.py` | 정확한 최종 판단 계약에 한정한 형식 정규화 |
| `single_object_closer.py` | 등록 함수의 유일한 닫는 중괄호 누락 후보, 엄격한 schema 검사와 원문 보존 |
| `claude_transport.py` | 별도 단일 Claude 구독 bridge 검토 소스 |
| `format_recovery_dispatch.py`, `process_dispatch.py` | 그 단일 bridge의 검토·보류·소유 process 정리 경계 |

`ClaudeProductGateway`와 공통 task 원문의 Opus5/high는 단일 bridge 소스의 identity입니다. 공개 두 구독 경로의 medium 설정과 구분합니다. `route_transport.route_task`는 명시적으로 선택한 경로의 실제 모델·effort를 입력 task에 반영합니다.

구문 helper는 EVIDA 프로젝트에서 작성한 순수 JSON 처리 코드입니다. 문자열 밖의 `}` 한 글자 삽입 중 정확한 등록 schema를 유일하게 통과하는 경우만 후보로 만들며, 원 문자열·수리 후보·위치와 hash 영수증을 보존합니다. 최종 판단이나 미등록/금지된 함수의 수리를 허용하지 않습니다. 독립 worker의 전체4초 상한과 내부1초 탐색 상한을 구분합니다. 구문 통과는 과학적 의미의 검증이 아니며 이후 제품의 원계약 검사가 계속 적용됩니다.

## 설치·연결 조건

이 폴더는 검토 가능한 연결 소스입니다. 전체 구독 adapter 런타임이나 인증된 독립 실행 환경을 제공하지 않습니다. 다음 구성을 별도로 갖추고 운영자의 검토를 거쳐야 합니다.

1. 제품·고정 과학 환경과 [`공식 start`](../scripts/start_reviewed_public_release.py), [`serve`](../scripts/serve_reviewed_public_release.py) 경로를 준비합니다. 모델·effort·store 예산은 명시한 실행 설정으로 연결합니다.
2. Claude·Codex CLI와 사용할 계정의 구독 인증, 검토된 외부 LROS/LAVA adapter 런타임을 준비합니다. 그 엔진 소스·인증·가중치는 여기에 복제하지 않습니다. 아래 helper의 공개/설치 권한과 버전은 해당 제공 경로에서 확인합니다.
3. 실제 source 배치는 `route_transport.py`의 `BRIDGE=<MODEL_ROUTES_RUNTIME>/bridge`, 같은 bridge 안의 계약·색인·구문 helper와 일치시킵니다. 공개 폴더의 평면 배치가 서버 설치 배치를 자동으로 생성하지는 않습니다. `EVIDA_SUBSCRIPTION_PRODUCT`는 검토된 제품 디렉터리 경로이며 key 값이 아닙니다.
4. 해당 설치의 source/runtime pin과 운영자 승인·review·hold 조건을 검토하고, 기존 운영을 잇는 경우 원래 공유 ledger·호출 번호를 보존합니다. 실제 승인 profile이나 그럴듯한 샘플 승인 파일은 제공하지 않습니다. 단순 경로·hash 검사 해제로 인증된 연결을 재현했다고 표현하지 않습니다.

별도 직접 의존성:

- target helper: `indexed_research_input`, `research_call_policy`, `research_input_support`, `bounded_subscription_dispatch`, `returned_reading_entry25`, `review_claude_context82`
- `lavi_research_os.models`, `policy`, `io`, `providers.*`, `c1.file_input`, `c1.source_navigation`, `c1.workflow`
- 설치 패키지 `jsonschema`, Python 표준 라이브러리와 제품의 `evida` 모듈

실제 import 목록은 manifest에 있습니다. 외부 런타임의 추가 전이 의존성·설치 권한은 그 배포판에서 확인합니다. 실행 결과나 인증 profile, 원 입력·모델 응답·DB는 소스에 포함하지 않습니다. source hash 일치는 운영 byte의 검토 범위를 뜻하며 별도 환경의 E2E 성공을 증명하지 않습니다. 전체 제품 기능은 [공개 EVIDA](https://evida.ndagentevida.com)에서 확인할 수 있습니다.
