"""Classify stale reassessment inputs without weakening publication validation."""
import json


class StaleReassessmentContextError(ValueError):
    def __init__(self, message, *, current_snapshot, previous_snapshot, draft_id=None):
        super().__init__(message)
        self.current_snapshot = current_snapshot
        self.previous_snapshot = previous_snapshot
        self.draft_id = draft_id


def repair_instruction(error, response_limit, *, synthesis_only=False):
    # Finite and explicitly synthesis-only requests retain their exact correction policy.
    if response_limit is not None or synthesis_only or not isinstance(error, StaleReassessmentContextError):
        return None
    binding = json.dumps({
        'classification': 'stale_reassessment_context',
        'current_snapshot_sha256': error.current_snapshot,
        'previous_snapshot_sha256': error.previous_snapshot,
        'stale_draft_id': error.draft_id,
        'publication_accepted': False,
    }, ensure_ascii=False, sort_keys=True)
    return (
        '방금 판단은 게시되지 않았습니다. 재검토 초안이 사용한 입력 묶음과 현재 입력 묶음이 다릅니다.\n'
        'REASSESSMENT_CONTEXT_REPAIR=' + binding + '\n'
        '이 무제한 정상 연구 경로에서는 필요한 재검토 도구를 사용할 수 있습니다. '
        '기존 과학적 주장·근거·관측·완료 계산과 실패 기록을 유지하세요. '
        '현재 실제 전달된 입력 묶음을 기준으로 최종 제안과 동일한 내용의 재검토 초안을 새로 작성하세요. '
        '필요한 상위 초안을 실제 받아 하위 초안에 연결하고, 이후 다른 상태 평가를 갱신하지 않은 채 '
        '실제 받은 최신 초안 내용을 그대로 최종 제안에 채택하세요. '
        '이전 초안 ID의 재제출, 검사 생략, 과학적 결론 변경 또는 계산 반복을 요구하는 안내가 아닙니다. '
        '최신 초안의 작업·입력·전달·내용·상위 연결 검사는 모두 그대로 적용됩니다. '
        '정상 게시 뒤 원래 연구 목표의 충족 여부를 검토하세요.'
    )
