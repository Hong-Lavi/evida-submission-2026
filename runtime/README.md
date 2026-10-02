# Claude 구독 연결 검토용 소스

이 폴더에는 공개 제품의 Opus5/high 구독 연결을 검토하는 Python 소스6개가 있습니다. 정확한 소스 버전은 묶음의 MANIFEST와, 최종 갱신 시 생성되는 RUNTIME_SOURCE_MANIFEST에서 확인합니다. 승인·원실패·정규화·공유 호출 번호·60회 상한·동시2개·읽기 범위를 검사하고 native Runner에 반환합니다.

필요한 외부 구성은 검수된 LROS0.4.0 기반 adapter 런타임, 실제 Claude CLI와 구독 인증, 운영자의 정확한 모델 권한·원인교정 review, 제품 경로입니다. 이 폴더는 인증된 독립 실행 환경을 제공하지 않습니다. API key·유료 fallback을 사용하지 않으며, 인증·실제 승인 profile·호출 영수증·DB·원 입력은 포함하지 않습니다.

소스6개가 직접 import하는 외부 helper는 다음과 같습니다.

- `indexed_research_input`, `research_call_policy`, `research_input_support`
- `bounded_subscription_dispatch`, `returned_reading_entry25`, `review_claude_context82`
- `lavi_research_os.models`, `policy`, `io`
- `lavi_research_os.providers.base`, `claude`, `codex`, `recording`
- `lavi_research_os.c1.file_input`, `source_navigation`, `workflow`
- 별도 설치한 `jsonschema` 및 이 묶음의 `evida` 모듈

실제 import가 최종 기준이며 외부 런타임의 추가 의존성은 해당 설치에서 확인해야 합니다. Codex provider 모듈을 import하는 공유 helper가 있으나, 이 구독 경로가 다른 제공자를 자동 실행한다는 뜻은 아닙니다.

코드 안의 approval/source SHA와 배포 경로는 검수된 서버 연결을 기록한 것입니다. 실제 권한 파일은 제공하지 않습니다. 임의 profile 생성이나 hash 검사 해제로 같은 연결을 재현했다고 주장할 수 없습니다. 다른 환경의 독립 인증 setup과 전체 E2E는 시험하지 않았습니다. 과거 server.Application의 API/Terra 기본값은 현재 구독 경로의 실행 안내가 아닙니다.

실제 실행 확인은 [공개 데모](https://evida.ndagentevida.com)를 사용합니다. 자체 설치는 과학 자원·인증·권한·제품 경로를 별도 검수해야 합니다. 외부 런타임·가중치의 배포 조건은 각 제공자·저자 조건을 확인하며, 포함한 seedmatchr/3Dmol/Pretendard 라이선스는 해당 vendor/fonts 경로에 보존합니다.
