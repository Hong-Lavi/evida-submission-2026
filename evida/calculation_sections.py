"""Exact, paginated author tables; no relevance filtering or recomputation."""
from copy import deepcopy
import hashlib
import json

SECTIONS = {
    'weightedSIF': ('전체 상호작용의 해 선택 가중치', False),
    'nodesAttributes': ('전체 노드의 해 선택 상태', False),
    'sifAll': ('반환된 각 경로의 원 연결', True),
    'attributesAll': ('반환된 각 경로의 노드 활성 부호', True),
}


def entries(value, section):
    if section not in SECTIONS:
        raise ValueError('목록에서 실제 계산표를 선택해 주세요.')
    table = value.get('author_result', {}).get(section)
    if not isinstance(table, list):
        raise ValueError('이 계산표가 반환되지 않았거나 지원하는 표 형식이 아닙니다. 빈 결과로 처리하지 않습니다.')
    grouped = SECTIONS[section][1]
    result = []
    for i, item in enumerate(table):
        if grouped:
            if not isinstance(item, list):
                raise ValueError('경로별 원 계산표 형식을 확인해야 합니다.')
            for j, row in enumerate(item):
                result.append({'source_path': ['author_result', section, str(i), str(j)],
                    'network_index': i + 1, 'value': deepcopy(row)})
        else:
            result.append({'source_path': ['author_result', section, str(i)], 'value': deepcopy(item)})
    return result


def presentation(value):
    """Keep every condition and normal result row; replace tables with addresses."""
    result = deepcopy(value)
    author = result.get('author_result')
    if not isinstance(author, dict):
        return result
    navigation = []
    for section, (label, _) in SECTIONS.items():
        if section not in author:
            continue
        try:
            rows = entries(value, section)
        except ValueError:
            # Unknown shapes remain explicit in the ordinary view, not silently dropped.
            continue
        raw = json.dumps(author.pop(section), ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
        navigation.append({'section': section, 'label': label, 'total_rows': len(rows),
            'source_path': ['author_result', section], 'section_sha256': hashlib.sha256(raw).hexdigest(),
            'read_function': 'read_calculation_section', 'offset': 0, 'limit': 30})
    result['calculation_sections'] = navigation
    result['calculation_reading_scope'] = (
        'This view pages the returned pathway rows and retains all interpretation conditions. '
        'Listed author tables are not included or claimed read; use read_calculation_section '
        'for exact rows, including zero/unselected entries. Original download is unchanged. '
        'Selection weights and activity states are solver outputs, not probabilities or measured biology.')
    return result


def read(value, section, offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('계산표 조회 범위가 올바르지 않습니다.')
    rows = entries(value, section)
    result = presentation(value)
    result.pop('rows', None)
    result.update(semantic_type='exact_calculation_section', source_semantic_type=value.get('semantic_type'),
        section=section, section_label=SECTIONS[section][0], rows=rows[offset:offset + limit],
        total_rows=len(rows), offset=offset, has_more=offset + limit < len(rows))
    return result
