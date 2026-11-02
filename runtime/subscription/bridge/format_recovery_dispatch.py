"""Explicit diagnosed-format transition. Missing exact ROOT receipt stays unavailable."""
from pathlib import Path
import hashlib,json
from process_dispatch import BoundedDispatch, DispatchPaused
BASE=Path(__file__).resolve().parent.parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

class FormatRecoveryDispatch(BoundedDispatch):
    def __init__(self, root, maximum=2, hold_path=None, *, recovery_review_path=None,
                 recovery_review_sha256=None, pins_path=None):
        super().__init__(root, maximum, hold_path)
        self.review_path=Path(recovery_review_path) if recovery_review_path else None
        self.review_sha=recovery_review_sha256
        self.pins_path=Path(pins_path) if pins_path else BASE/'diagnosed-cause-pins.json'
    def transition(self):
        try:
            if not self.review_path or not self.review_sha or sha(self.review_path)!=self.review_sha:
                raise ValueError('Exact ROOT format-repair review not supplied')
            review=json.loads(self.review_path.read_text());pins=json.loads(self.pins_path.read_text())
            if review.get('diagnosed_cause_pins_sha256') != sha(self.pins_path):
                raise ValueError('Exact diagnosed cause/source profile required')
            if (review.get('status')!='ROOT_REVIEWED_DIAGNOSED_ORIGINAL_VALIDATIONERROR_REPAIRED'
                or review.get('automatic_resume') is not False
                or review.get('new_requests_only') is not True
                or review.get('original_study_retry_authorized') is not False
                or review.get('scientific_content_acceptance')!='SEPARATE_REVIEW_REQUIRED'
                or review.get('model')!='claude-opus-5' or review.get('effort')!='high'
                or review.get('provider_calls')!=str(self.root.resolve())):
                raise ValueError('Reviewed transition scope missing or changed')
            for key in ['predecessor_hold','original_failed_call_receipt']:
                if review.get(key)!=pins[key] or review.get(key+'_sha256')!=pins[key+'_sha256'] or sha(pins[key])!=pins[key+'_sha256']:
                    raise ValueError('Diagnosed original evidence changed')
            # Preserve the reviewed input-repair03 -> format04 ancestry. This new
            # transition is scoped only to call39, never a general hold release.
            if review.get('diagnosed_cause') != pins.get('diagnosed_cause') or pins.get('diagnosed_cause') != 'CALL39_INSPECT_ARTIFACT_NULL_NAME_NOTE_UNUSED':
                raise ValueError('Exact newly diagnosed metadata cause required')
            if review.get('preservation_manifest_sha256') != pins.get('preservation_manifest_sha256') or sha(pins['preservation_manifest']) != pins['preservation_manifest_sha256']:
                raise ValueError('Original runtime04/input authority chain review required')
            preserved=json.loads(Path(pins['preservation_manifest']).read_text())
            for path, expected in preserved['files'].items():
                if sha(path) != expected:
                    raise ValueError('Preserved ancestor/call39 source changed')
            hold=json.loads(Path(pins['predecessor_hold']).read_text())
            failed=json.loads(Path(pins['original_failed_call_receipt']).read_text())
            if hold.get('reason')!='ValidationError' or failed.get('error_type')!='ValidationError' or failed.get('status')!='FAILED':
                raise ValueError('Only the exact diagnosed validation failure can transition')
            if review.get('normalization_receipt_sha256')!=sha(pins['original_normalization_receipt']):
                raise ValueError('Exact successful format normalization evidence required')
            if review.get('normalizer_sha256')!=pins['normalizer_sha256']:
                raise ValueError('Normalizer source review missing')
            files=review.get('repaired_source_files',{})
            if set(files)!=set(pins['candidate_source_files']):
                raise ValueError('Exact candidate source review required')
            for path,h in files.items():
                if h!=pins['candidate_source_files'][path] or sha(path)!=h:
                    raise ValueError('Reviewed repair source changed')
            return {'state':'EXPLICIT_DIAGNOSED_FORMAT_TRANSITION','review_sha256':self.review_sha,'predecessor_preserved':True,'new_requests_only':True}
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise DispatchPaused('Format repair requires exact ROOT review: '+str(exc)) from None
    def check_dispatch(self):
        super().check_dispatch()  # Any new/local failure is sticky and never normalized away.
        self.transition()
    def snapshot(self):
        result=super().snapshot()
        try: result['format_transition']=self.transition()
        except DispatchPaused as exc:
            result['paused']=True;result['format_transition']={'state':'PREPARED_UNAVAILABLE','reason':str(exc)}
        return result
