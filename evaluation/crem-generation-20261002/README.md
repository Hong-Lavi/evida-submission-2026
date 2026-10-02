# 공개 구조 생성 평가

**[전체 조건·20과제 행·실제 반환 결과](README_CREM.md)**에서 실행 조건, 중단과 완료,
구조의 유효성·동일성·출처를 확인할 수 있습니다. 완료한5과제의300반환 구조에 대한
제품 원기록을 재검산했습니다. 과제 안 고유 입체 구조 수의 합은299이며, 해당 과제의
전체 공식 학습 구조에 없는 수는288입니다.

- `reproduce_crem_metrics.py`: 보존된20행에서 집계와 기술적 구간을 재계산합니다.
- `returned-structures.csv`: 완료5과제의 실제 반환300행과 출발 구조·변환입니다.
- `verify_returned_structures.py`: RDKit으로300반환의 구조·과제 내 중복을 다시 확인합니다.
  `--official-dir`로 공식 MoleculeACE CSV 폴더를 제공하면 원입력과 전체 학습 대비
  신규성도 재검산합니다. 다운로드·새 생성·모델 추론은 실행하지 않습니다.
- `returned-structure-sources.json`: 공식 자료 판본과 원파일, native 반환·열거 기록 해시입니다.

예시:

```bash
python reproduce_crem_metrics.py
python verify_returned_structures.py --official-dir /path/to/MoleculeACE/Data/benchmark_data
```

공식 입력 자료는 [MoleculeACE 저자 저장소](https://github.com/molML/MoleculeACE)의
고정판본을 사용했습니다. 원데이터와 라이선스·인용은 해당 저자 자료를 따릅니다.
공개 반환 구조는 이번 계산 결과이며 원출처를 보존합니다. 구조의 신규성은 명시된
자료 집합과 비교한 값이고 실제 합성·약리 효능은 후속 실험의 확인 항목입니다.
