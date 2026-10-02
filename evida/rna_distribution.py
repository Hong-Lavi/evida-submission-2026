"""Descriptive distributions from explicit, already chosen RNA weights.

No matching, fitted model, significance test or biological interpretation is
performed here. All supplied rows and zero weights remain part of the input.
"""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np


def analyze(value):
    if value.get("semantic_type") != "rna_fixed_weight_observations":
        raise ValueError("출처와 고정 가중치가 명시된 RNA 비교 입력이 필요합니다.")
    rows = value.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("비교할 실제 관측 행이 없습니다.")
    cases = defaultdict(list)
    seen = set()
    for row in rows:
        identity = (row.get("case"), row.get("gene_id"))
        if not all(isinstance(x, str) and x for x in identity) or identity in seen:
            raise ValueError("비교 조건과 고유 유전자 ID를 확인해 주세요.")
        seen.add(identity)
        numbers = [row.get(k) for k in ("log2FoldChange", "target_weight", "background_weight")]
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in numbers):
            raise ValueError("결측·비유한 관측을 자동 제외하지 않습니다. 입력을 확인해 주세요.")
        if numbers[1] < 0 or numbers[2] < 0 or numbers[1] * numbers[2] > 0:
            raise ValueError("서로 겹치지 않는 두 집합의 음수가 아닌 가중치가 필요합니다.")
        cases[identity[0]].append(numbers)
    results = []
    for case, items in sorted(cases.items()):
        a = np.asarray(items, dtype=float)
        x, t, b = a.T
        tm, bm = math.fsum(t), math.fsum(b)
        if tm <= 0 or bm <= 0 or not math.isfinite(tm + bm):
            raise ValueError("두 집합 모두 양의 유한 가중치가 필요합니다.")
        t, b = t / tm, b / bm
        support, inverse = np.unique(x, return_inverse=True)
        delta = np.cumsum(np.bincount(inverse, weights=t)) - np.cumsum(np.bincount(inverse, weights=b))
        mean = float(np.dot(x, t - b))
        integral = -float(np.dot(np.diff(support), delta[:-1]))
        if abs(mean - integral) > 1e-9 or abs(delta[-1]) > 1e-9:
            raise ValueError("평균과 전체 누적분포의 일치 검사를 통과하지 못했습니다.")
        results.append({"row_id": case, "case": case, "input_rows": len(items),
            "target_Q": int((t > 0).sum()), "background_nonzero": int((b > 0).sum()),
            "target_weight_sum": tm, "background_weight_sum": bm,
            "mean_difference": mean, "maximum_positive_difference": float(max(0, delta.max())),
            "minimum_difference": float(min(0, delta.min())),
            "maximum_location": float(support[delta.argmax()]),
            "minimum_location": float(support[delta.argmin()]),
            "crosses": bool(delta.max() > 1e-12 and delta.min() < -1e-12),
            "full_support_points": len(support), "full_curve_integral_check_error": abs(mean - integral)})
    return {"status": "succeeded", "semantic_type": "rna_fixed_weight_distribution",
        "summary": {"comparisons": len(results), "input_rows": len(rows),
                    "crossing_comparisons": sum(r["crosses"] for r in results)},
        "context": value.get("context"), "sources": value.get("sources", []), "rows": results,
        "limits": ["보존한 관측·고정 가중치의 기술적 비교입니다. 새 실험·매칭 재적합·유의성 검정은 아닙니다.",
                   "평균 차이와 전체 분포의 교차를 구분합니다. 일반 KS p값을 가중 분포에 붙이지 않습니다.",
                   "전사체 비교로 동물 간 변동·직접 seed 결합·단백질 효과를 확인한 것은 아닙니다."]}
