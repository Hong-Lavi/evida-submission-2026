"""Independent Decimal evaluation, adapted from the recorded review utility.

No EVIDA product validator, numerical library, solver or network is imported.
"""
import csv
import io
import re
from decimal import Decimal as D

NUMBER = r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
TERM = re.compile(r'\s*([+-]?)\s*(' + NUMBER + r')?\s*([A-Za-z_][A-Za-z_0-9]*)')


def expression(s):
    out = []; pos = 0
    while s[pos:].strip():
        m = TERM.match(s, pos)
        if not m:
            raise ValueError('Unparsed expression.')
        sign, coefficient, var = m.groups()
        if out and not sign:
            raise ValueError('Missing term separator.')
        out.append((var, D(coefficient or '1') * (-1 if sign == '-' else 1)))
        pos = m.end()
    return out


def solution(text):
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ['name', 'solution']:
        raise ValueError('Unexpected full-vector columns.')
    rows = list(reader); values = {r['name']: D(r['solution']) for r in rows}
    if len(values) != len(rows) or not all(x.is_finite() for x in values.values()):
        raise ValueError('Duplicate or nonfinite solution variable.')
    return values


def recompute(text, csv_text):
    v = solution(csv_text)
    dot = lambda expr: sum((c * v[n] for n, c in expression(expr)), D(0))
    bounds = {}; integers = set(); binary = set(); constraints = []; objective = None
    section = None; seen = []
    headings = ['Minimize', 'Subject To', 'Bounds', 'Binaries', 'Generals', 'End']
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in headings:
            section = line; seen.append(line); continue
        if section == 'Minimize':
            if objective is not None or not line.startswith('Obj:'):
                raise ValueError('Unexpected objective.')
            objective = line.split(':', 1)[1]
        elif section == 'Subject To':
            label, body = line.split(':', 1)
            lhs, op, rhs = re.split(r'\s*(<=|>=|=)\s*', body)
            res = dot(lhs) - D(rhs)
            constraints.append((label, abs(res) if op == '=' else max(D(0), res if op == '<=' else -res)))
        elif section == 'Bounds':
            lo, n, hi = [x.strip() for x in line.split('<=')]
            if n in bounds:
                raise ValueError('Duplicate bound.')
            bounds[n] = D(lo), D(hi)
        elif section in ['Binaries', 'Generals']:
            if line in integers:
                raise ValueError('Duplicate integer declaration.')
            integers.add(line)
            if section == 'Binaries':
                binary.add(line)
        else:
            raise ValueError('Unrecognized LP section.')
    if seen != headings or set(v) != set(bounds) or not integers <= set(v):
        raise ValueError('Incomplete LP/vector pairing.')
    if len({n for n, _ in constraints}) != len(constraints):
        raise ValueError('Duplicate constraint.')
    cv = max(r for _, r in constraints)
    bv = max(max(D(0), lo - v[n], v[n] - hi) for n, (lo, hi) in bounds.items())
    iv = max(abs(v[n] - v[n].to_integral_value()) for n in integers)
    terms = expression(objective)
    err = sum((c * v[n] for n, c in terms if n.startswith('aD')), D(0))
    penalty = sum((c * v[n] for n, c in terms if re.fullmatch(r'n[UD]\d+', n)), D(0))
    return {'valid': max(cv, bv, iv) <= D('0.000001') and all(D(0) <= v[n] <= D(1) for n in binary),
            'variables': len(v), 'constraints': len(constraints), 'bounds': len(bounds),
            'integer_variables': len(integers), 'objective': str(dot(objective)),
            'weighted_sign_error': str(err), 'state_penalty': str(penalty),
            'max_constraint_violation': str(cv), 'max_bound_violation': str(bv),
            'max_integrality_violation': str(iv)}
