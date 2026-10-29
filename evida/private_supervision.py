"""Private opt-in response policy; None is unbounded, never a large finite sentinel."""
from itertools import count
import hashlib
import json


def checked_limit(value):
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError('response_limit must be None or a positive integer')
    return value


def response_indices(first, limit, corrections):
    checked_limit(limit)
    return count(first) if limit is None else iter(range(first, limit + corrections))


def response_state(index, limit, corrections, *, synthesis_only=False, framed=False, correction_limit=2):
    checked_limit(limit)
    correcting = limit is not None and (corrections > 0 or index >= limit)
    synthesize = correcting or (synthesis_only and framed) or (limit is not None and index == limit - 1)
    return dict(correcting=correcting, synthesize=synthesize,
                maximum_remaining=None if limit is None else limit + correction_limit - index,
                research_remaining=None if limit is None else 0 if synthesize else max(0, limit-index))


class ActionMonitor:
    """Repeated action/errors signal a supervisor; never stop by a count or retry a refusal."""
    def __init__(self):
        self.last=None
        self.repeated=0
        self.responses=0

    def observe(self, result):
        actions=[]
        for item in result.get('output',[]):
            if item.get('type')=='function_call':
                arguments=item.get('arguments')
                try:
                    arguments=json.loads(arguments) if isinstance(arguments,str) else arguments
                    if isinstance(arguments,dict):
                        arguments={k:v for k,v in arguments.items() if k!='research_notes'}
                except (ValueError,TypeError):
                    pass
                actions.append({'name':item.get('name'),'arguments':arguments})
        body=json.dumps(actions,sort_keys=True,ensure_ascii=False).encode()
        signature=hashlib.sha256(body).hexdigest() if actions else None
        self.repeated=self.repeated+1 if signature is not None and signature==self.last else 1 if signature else 0
        self.last=signature
        self.responses+=1
        return dict(response_number=self.responses,action_names=[a['name'] for a in actions],
                    action_signature=signature,identical_action_streak=self.repeated,
                    schema_rejection=bool(result.get('schema_rejection')),
                    supervisor_attention=self.repeated>=3 or bool(result.get('schema_rejection')),
                    automatic_stop=False,automatic_retry=False,
                    meaning='Action repetition is an observation, not proof of scientific failure. '
                            'Supervisor examines goal, new evidence, errors and current artifacts.')
