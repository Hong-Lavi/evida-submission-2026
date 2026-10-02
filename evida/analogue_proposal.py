"""Generate source-linked structure hypotheses from retrieved compounds.

Use CReM context-constrained fragment transformations when available, or single-cut
matched molecular pair recombination of retrieved cores and substituents. Preserve
structure origins, declared comparators and existing chemistry filters.

This module enumerates proposals. The connected science worker separately fits a
model to retained activity records and attaches predictions only when its unseen-
scaffold holdout is usable; requested guided rounds use that model for bounded
search. Neither generated structure nor prediction is measured function or efficacy.
Choose the next source-linked activity/function comparison from the research
hypothesis and competing explanations. Docking is not a mandatory next step, and
its score relative to a parent does not automatically reject a proposal.

Runs in the pinned science runtime. This module performs no network lookup.
"""
import os
import pathlib
import sys
import tempfile
import time
import xml.parsers.expat  # noqa: F401  - load stdlib expat before RDKit's linked libraries

MAXIMUM_SUBSTITUENT_HEAVY_ATOMS = 14  # a substituent, not a second molecule
SYNTHETIC_ACCESSIBILITY_CUTOFF = 4.0  # Ertl & Schuffenhauer's "readily accessible" convention
MAXIMUM_INPUTS = 120
MAXIMUM_ENUMERATED = 60000
EMBED_SEED = 20260930  # ETKDG defaults to an unseeded generator; an unrepeatable row is not a record

# Valence-legal but chemically unstable motifs that recombination can create. RDKit sanitises
# them without complaint and the synthetic-accessibility score does not penalise them, so a
# proposal carrying one would look perfectly reasonable in the table. Measured: 51 of 3,785.
UNSTABLE_MOTIFS = {
    'hemiaminal': '[OX2H1][CX4]([#7])',
    'gem_halo_alcohol': '[OX2H1][CX4]([F,Cl,Br,I])',
    'gem_diol': '[OX2H1][CX4][OX2H1]',
    'aminal': '[#7][CX4]([#7])',
    'enol': '[OX2H1][CX3]=[CX3]',
    'acyl_halide': '[CX3](=O)[F,Cl,Br,I]',
    'orthoester': '[CX4]([OX2])([OX2])[OX2]',
    'peroxide': '[OX2][OX2]',
    'anhydride': '[CX3](=O)[OX2][CX3]=O',
}

PROPERTY_WINDOW = {'mw': (250.0, 650.0), 'logp': (-1.0, 6.0),
                   'donors': 5, 'acceptors': 10, 'rotatable': 12, 'tpsa': 150.0}


# Widening the box by the same margin for every run would loosen the filter everywhere. Taking it
# from the retrieved set loosens it exactly where that target's own chemistry already lives, and
# nowhere else. The generic bound stays the floor, so a narrow retrieved set cannot tighten it.
PROPERTY_MARGIN = {'mw': 60.0, 'logp': 0.8, 'tpsa': 20.0, 'donors': 1, 'acceptors': 2,
                   'rotatable': 2}


def _properties(molecule, chem):
    Descriptors, rdMolDescriptors = chem
    return {'mw': Descriptors.MolWt(molecule), 'logp': Descriptors.MolLogP(molecule),
            'donors': Descriptors.NumHDonors(molecule),
            'acceptors': Descriptors.NumHAcceptors(molecule),
            'rotatable': Descriptors.NumRotatableBonds(molecule),
            'tpsa': rdMolDescriptors.CalcTPSA(molecule)}



def _alert_catalog():
    from rdkit.Chem import FilterCatalog
    parameters = FilterCatalog.FilterCatalogParams()
    for catalog in (FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS,
                    FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK,
                    FilterCatalog.FilterCatalogParams.FilterCatalogs.NIH):
        parameters.AddCatalog(catalog)
    return FilterCatalog.FilterCatalog(parameters)



# Above this share of proposals sitting at or above this similarity, the descriptor has stopped
# telling proposals apart rather than telling us they are all close.
SATURATED_SIMILARITY = 0.99
SATURATED_SHARE = 0.9


def similarity_saturation(rows):
    """Whether tanimoto_to_nearest still discriminates for this chemistry.

    Measured on the IPF run: 40 of 40 proposals returned 1.0 against different structures. The
    Morgan fingerprint saturates on long aliphatic chains, so the applicability-domain check
    passes trivially and the number reads as a verification it did not perform.
    """
    values = [row['tanimoto_to_nearest'] for row in (rows or ())
              if isinstance(row, dict) and isinstance(row.get('tanimoto_to_nearest'), (int, float))]
    if not values:
        return {'saturated': False, 'proposals': 0, 'at_or_near_one': 0,
                'lowest': None, 'highest': None, 'meaning': None}
    near = sum(1 for v in values if v >= SATURATED_SIMILARITY)
    saturated = near >= max(3, SATURATED_SHARE * len(values))
    return {'saturated': saturated, 'proposals': len(values), 'at_or_near_one': near,
            'lowest': min(values), 'highest': max(values),
            'meaning': ('제안 대부분이 회수 구조와 2D 유사도 1.0으로 나왔습니다. 이 화학에서는 '
                        'Morgan 지문이 포화해 구조를 구별하지 못한다는 뜻이며, 제안이 실제로 '
                        '같다는 뜻이 아닙니다. 이 값으로 한 적용 범위 판정은 이번 실행에서 '
                        '변별력이 없습니다. 정확한 구조와 변환 출처를 확인하고, 적용 범위는 모델의 학습·검증 조건과 가설에 맞는 활성·기능 근거로 검토하세요.')
                       if saturated else None}


def alerts_shared_with_retrieved(rows):
    """Which alert names the target's own retrieved ligands already carry.

    Measured on the IPF run: 25 of 25 retrieved LPAR1 ligands trip an alert and 0 pass, the
    commonest being Aliphatic_long_chain and phosphor - which is what a lysophosphatidic acid
    analogue is. An alert the known actives all carry says something about the target class, not
    about a proposal.
    """
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    alerts = _alert_catalog()
    names, seen, unreadable = set(), 0, 0
    for row in rows or ():
        smiles = (row or {}).get('smiles') if isinstance(row, dict) else row
        molecule = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) and smiles else None
        if molecule is None:
            unreadable += 1
            continue
        seen += 1
        for hit in alerts.GetMatches(molecule):
            names.add(hit.GetDescription())
    return {'names': names, 'compounds': seen, 'unreadable': unreadable,
            'meaning': '이 표적에서 회수한 화합물들이 이미 가지고 있는 구조 경보입니다. '
                       '제안이 같은 경보를 가졌다고 버리지 않고 기록만 합니다. '
                       '이것은 그 substructure가 안전하다는 뜻이 아닙니다 — '
                       '이 표적의 알려진 물질과 같은 특징이라는 뜻일 뿐입니다.'}


def split_alert_names(shared, hit):
    """Alerts that reject, and alerts the retrieved set already carries."""
    hit = set(hit or ())
    carried = hit & set(shared or ())
    return hit - carried, carried


def effective_property_window(rows):
    """The generic drug-like box, widened to admit what this research actually retrieved.

    A proposal rejected for occupying the same space as the target's own known ligands is not
    being filtered, it is being misread. Measured on the first real run: 0 of 25 retrieved LPAR1
    actives passed the generic box, and all 3,762 enumerated structures were dropped by it.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDLogger.DisableLog('rdApp.*')
    chem = (Descriptors, rdMolDescriptors)

    seen, unreadable = [], 0
    for row in rows or ():
        smiles = (row or {}).get('smiles') if isinstance(row, dict) else row
        molecule = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) and smiles else None
        if molecule is None:
            unreadable += 1
            continue
        seen.append(_properties(molecule, chem))

    window = {k: (tuple(v) if isinstance(v, tuple) else v) for k, v in PROPERTY_WINDOW.items()}
    if not seen:
        return {'window': window, 'generic': dict(PROPERTY_WINDOW), 'observed': None,
                'retrieved_all_inside': True, 'unreadable': unreadable, 'basis': 'generic_only',
                'meaning': '회수한 구조가 없어 일반 물성창을 그대로 씁니다.'}

    observed = {}
    for key in ('mw', 'logp', 'donors', 'acceptors', 'rotatable', 'tpsa'):
        values = [row[key] for row in seen]
        observed[key] = (min(values), max(values))

    for key in ('mw', 'logp'):
        low, high = PROPERTY_WINDOW[key]
        window[key] = (min(low, observed[key][0] - PROPERTY_MARGIN[key]),
                       max(high, observed[key][1] + PROPERTY_MARGIN[key]))
    for key in ('donors', 'acceptors', 'rotatable', 'tpsa'):
        window[key] = max(PROPERTY_WINDOW[key], observed[key][1] + PROPERTY_MARGIN[key])

    inside = all(window['mw'][0] <= row['mw'] <= window['mw'][1]
                 and window['logp'][0] <= row['logp'] <= window['logp'][1]
                 and row['donors'] <= window['donors'] and row['acceptors'] <= window['acceptors']
                 and row['rotatable'] <= window['rotatable'] and row['tpsa'] <= window['tpsa']
                 for row in seen)
    return {'window': window, 'generic': dict(PROPERTY_WINDOW), 'observed': observed,
            'retrieved_all_inside': inside, 'unreadable': unreadable, 'compounds': len(seen),
            'basis': 'generic_union_retrieved',
            'meaning': '일반 물성창에 이 연구가 회수한 구조들이 실제로 차지하는 범위를 더한 것입니다. '
                       '알려진 활성물질을 닮았다는 이유로 제안이 버려지는 것을 막습니다. '
                       '통과는 물성이 범위 안이라는 뜻이며 활성이나 안전의 근거가 아닙니다.'}


LIMITS = [
    '제안 구조 자체는 열거(enumeration) 결과입니다. 연결된 활성 모델의 조건부 예측과 구분하며, 구조 생성만으로 표적 결합이나 기능을 확인한 것은 아닙니다.',
    'core와 치환기는 모두 이 실행이 이미 회수한 화합물에서만 나왔습니다. 새로 내려받은 라이브러리가 없습니다.',
    'SA_score는 합성 난이도 추정치이며 실제 합성 가능성이나 경로를 보장하지 않습니다.',
    'tanimoto_to_nearest는 회수된 물질과의 2D 구조 유사도일 뿐 활성 전이를 뜻하지 않습니다. '
    '유사도가 높아도 활성이 크게 다른 경우(activity cliff)가 이 분야의 표준 관찰입니다.',
    '구조 경보 필터(PAINS/BRENK/NIH) 통과는 알려진 경보 substructure에 걸리지 않았다는 뜻이며 '
    '안전하다는 뜻이 아닙니다.',
    '다음 비교는 가설·측정 조건·경쟁 설명에 맞는 활성·기능 근거에 연결합니다. 도킹 점수나 모화합물 대비 점수만으로 제안을 자동 폐기하지 않습니다.',
]


def retrieved_smiles(value, limit=MAXIMUM_INPUTS):
    """The structure strings this research already stored, in recorded order."""
    from .structure_depiction import row_smiles
    found, seen = [], set()
    rows = value.get('rows') if isinstance(value, dict) else None
    for row in rows or []:
        smiles = row_smiles(row)
        if smiles and smiles not in seen:
            seen.add(smiles)
            found.append({'smiles': smiles,
                          'candidate_id': row.get('candidate_id') or row.get('entity_id'),
                          'name': row.get('name')})
        if len(found) >= limit:
            break
    return found


CREM_RADII = (1, 2, 3)
CREM_MAXIMUM_PER_SEED = 400


def crem_available():
    try:
        import crem.crem  # noqa: F401
        return True
    except Exception:
        return False


def crem_candidates(seeds, origin, work, arguments, chem):
    """Context-constrained transformations of each retrieved compound.

    Returns (candidates, detail). A candidate carries the seed it was transformed from and the
    exact transformation, so a reader can see what changed rather than only the result. The
    donor of the replacement fragment is the retrieved set this database was built from, which
    is recorded as the set name - never a shipped library.
    """
    import subprocess
    from crem.crem import mutate_mol
    work.mkdir(parents=True, exist_ok=True)
    listing = work / 'retrieved.smi'
    listing.write_text(''.join(f'{smiles}\t{origin.get(smiles, smiles)}\n' for smiles in seeds))
    database = work / 'fragments.db'
    build = subprocess.run([str(pathlib.Path(sys.executable).with_name('cremdb_create')),
                            '-i', str(listing), '-o', str(database), '-s', 'retrieved',
                            '-r', *[str(r) for r in CREM_RADII], '-c', '2'],
                           capture_output=True, text=True, timeout=900)
    if build.returncode != 0 or not database.is_file():
        raise RuntimeError('fragment database build failed: ' + build.stderr[-300:])
    candidates, seen = [], set(seeds)
    seed_total = int(arguments.get('maximum_proposals') or 25) * 8
    for smiles, molecule in seeds.items():
        for radius in CREM_RADII:
            for result in mutate_mol(molecule, str(database), radius=radius, min_size=0, max_size=10,
                                     max_replacements=min(CREM_MAXIMUM_PER_SEED, seed_total),
                                     return_rxn=True, ncores=2, seed=int(arguments.get('seed') or EMBED_SEED)):
                proposed, transformation = result[0], result[1]
                if proposed in seen:
                    continue
                seen.add(proposed)
                candidates.append({'smiles': proposed, 'seed': smiles,
                                   'transformation': transformation, 'context_radius': radius})
    detail = {'method': 'crem_context_constrained_fragment_transformation',
              'fragment_database': {'built_from': 'the compounds this research retrieved',
                                    'set_name': 'retrieved', 'radii': list(CREM_RADII),
                                    'compounds': len(seeds), 'bytes': database.stat().st_size},
              'versions': {'crem': _version('crem')}}
    return candidates, detail


def _version(name):
    import importlib.metadata
    try:
        return importlib.metadata.version(name)
    except Exception:
        return 'unknown'


def _fragments(molecule, chem, mmpa):
    """Single-cut core/substituent pairs of one molecule."""
    for _, chains in mmpa.FragmentMol(molecule, maxCuts=1, resultsAsMols=False):
        if not chains:
            continue
        parts = chains.split('.')
        if len(parts) != 2:
            continue
        built = [chem.MolFromSmiles(p) for p in parts]
        if any(b is None for b in built):
            continue
        if built[0].GetNumHeavyAtoms() >= built[1].GetNumHeavyAtoms():
            core, substituent, small = parts[0], parts[1], built[1]
        else:
            core, substituent, small = parts[1], parts[0], built[0]
        if small.GetNumHeavyAtoms() <= MAXIMUM_SUBSTITUENT_HEAVY_ATOMS:
            yield core, substituent


def _join(core, substituent, chem):
    """Bond the two dummy atoms together, or return None when that cannot be done cleanly."""
    combined = chem.MolFromSmiles(core + '.' + substituent)
    if combined is None:
        return None
    try:
        editable = chem.RWMol(combined)
        dummies = [a.GetIdx() for a in editable.GetAtoms() if a.GetAtomicNum() == 0]
        if len(dummies) != 2:
            return None
        first = editable.GetAtomWithIdx(dummies[0]).GetNeighbors()[0].GetIdx()
        second = editable.GetAtomWithIdx(dummies[1]).GetNeighbors()[0].GetIdx()
        editable.AddBond(first, second, chem.BondType.SINGLE)
        for index in sorted(dummies, reverse=True):
            editable.RemoveAtom(index)
        joined = editable.GetMol()
        chem.SanitizeMol(joined)
        return joined
    except Exception:
        return None


def propose_from(rows, arguments, work=None):
    """One round of proposals treating `rows` as the retrieved set. Same filters, same shape."""
    return propose({'rows': rows}, {**arguments, 'work_directory': work})


def propose(value, arguments):
    """value: a stored candidate view. arguments: {'reason': str, 'maximum_proposals': int}."""
    from rdkit import Chem, DataStructs, RDConfig, RDLogger, rdBase
    from rdkit.Chem import (AllChem, Descriptors, FilterCatalog, QED, rdFingerprintGenerator,
                            rdMMPA, rdMolDescriptors)
    from rdkit.Chem.Scaffolds import MurckoScaffold
    sys.path.append(os.path.join(RDConfig.RDContribDir, 'SA_Score'))
    import sascorer
    RDLogger.DisableLog('rdApp.*')

    started = time.time()
    wanted = int(arguments.get('maximum_proposals') or 25)
    inputs = retrieved_smiles(value)
    if len(inputs) < 2:
        return {'status': 'no_retrieved_structures',
                'rows': [], 'summary': {'retrieved_inputs': len(inputs)},
                'meaning': '구조 문자열을 가진 회수 화합물이 2개 미만이라 재조합할 것이 없습니다. '
                           '이것은 후보가 없다는 뜻이 아니라 이 자료에 구조가 없다는 뜻입니다.',
                'limits': LIMITS}

    seeds, unparsable = {}, []
    origin = {}
    for entry in inputs:
        molecule = Chem.MolFromSmiles(entry['smiles'])
        if molecule is None:
            unparsable.append(entry['smiles'])
            continue
        canonical = Chem.MolToSmiles(molecule)
        seeds[canonical] = molecule
        origin.setdefault(canonical, entry.get('candidate_id') or entry.get('name') or canonical)

    cores, substituents = {}, {}
    for canonical, molecule in seeds.items():
        for core, substituent in _fragments(molecule, Chem, rdMMPA):
            cores.setdefault(core, canonical)
            substituents.setdefault(substituent, canonical)

    # An input redrawn without stereochemistry is the same compound, not a proposal. Measured: 26.
    def flat(molecule):
        return Chem.MolToSmiles(Chem.MolFromSmiles(Chem.MolToSmiles(molecule, isomericSmiles=False)))

    flattened = {flat(m) for m in seeds.values()}
    seen, enumerated, stereoisomers = set(seeds), [], 0
    method = arguments.get('method') or ('crem' if crem_available() else 'mmp')
    generator_detail, generator_error = {}, None
    if method == 'crem':
        try:
            work = pathlib.Path(arguments.get('work_directory') or tempfile.mkdtemp(prefix='crem-'))
            produced, generator_detail = crem_candidates(seeds, origin, work / 'crem', arguments, Chem)
            for item in produced:
                molecule = Chem.MolFromSmiles(item['smiles'])
                if molecule is None or item['smiles'] in seen:
                    continue
                if flat(molecule) in flattened:
                    stereoisomers += 1
                    continue
                seen.add(item['smiles'])
                enumerated.append((item['smiles'], item['seed'], item['seed'], None, None, item))
        except Exception as error:  # a generator that cannot run must say so, not fall silent
            generator_error = f'{type(error).__name__}: {str(error)[:200]}'
            method, enumerated = 'mmp', []
    if method == 'mmp':
        for core, core_source in cores.items():
            for substituent, substituent_source in substituents.items():
                if len(enumerated) >= MAXIMUM_ENUMERATED:
                    break
                joined = _join(core, substituent, Chem)
                if joined is None:
                    continue
                smiles = Chem.MolToSmiles(joined)
                if smiles in seen:
                    continue
                if flat(joined) in flattened:
                    stereoisomers += 1
                    continue
                seen.add(smiles)
                enumerated.append((smiles, core_source, substituent_source, core, substituent, None))
        generator_detail = {'method': 'single_cut_matched_molecular_pair_recombination',
                            'observed_cores': len(cores), 'observed_substituents': len(substituents)}

    parameters = FilterCatalog.FilterCatalogParams()
    for catalog in (FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS,
                    FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK,
                    FilterCatalog.FilterCatalogParams.FilterCatalogs.NIH):
        parameters.AddCatalog(catalog)
    alerts = FilterCatalog.FilterCatalog(parameters)
    unstable = {name: Chem.MolFromSmarts(pattern) for name, pattern in UNSTABLE_MOTIFS.items()}
    # Chirality must be in the fingerprint, or an epimer of an input reads as a perfect match.
    fingerprints = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048,
                                                             includeChirality=True)
    seed_prints = {k: fingerprints.GetFingerprint(v) for k, v in seeds.items()}
    seed_scaffolds = {Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(v)) for v in seeds.values()}
    names, prints = list(seed_prints), list(seed_prints.values())

    # Anchored to the retrieved chemistry, because a fixed box rejected 100% of both the
    # proposals and the target's own known actives on the first real run.
    seed_structures = [{'smiles': Chem.MolToSmiles(m)} for m in seeds.values()]
    bounds = effective_property_window(seed_structures)
    window = bounds['window']
    # An alert every retrieved ligand carries describes the target class, not the proposal.
    shared_alerts = alerts_shared_with_retrieved(seed_structures)
    dropped = {'property_window': 0, 'synthetic_accessibility': 0,
               'structural_alert': 0, 'unstable_motif': 0}
    # What the old fixed box would have dropped, so the change stays measurable rather than
    # asserted. Nothing is filtered by this count.
    would_have_dropped_generic = 0
    rows = []
    for smiles, core_source, substituent_source, core, substituent, extra in enumerated:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            continue
        mass, logp = Descriptors.MolWt(molecule), Descriptors.MolLogP(molecule)
        polar = rdMolDescriptors.CalcTPSA(molecule)
        donors, acceptors = Descriptors.NumHDonors(molecule), Descriptors.NumHAcceptors(molecule)
        rotatable = Descriptors.NumRotatableBonds(molecule)
        if not (PROPERTY_WINDOW['mw'][0] <= mass <= PROPERTY_WINDOW['mw'][1]
                and PROPERTY_WINDOW['logp'][0] <= logp <= PROPERTY_WINDOW['logp'][1]
                and donors <= PROPERTY_WINDOW['donors']
                and acceptors <= PROPERTY_WINDOW['acceptors']
                and rotatable <= PROPERTY_WINDOW['rotatable']
                and polar <= PROPERTY_WINDOW['tpsa']):
            would_have_dropped_generic += 1
        if not (window['mw'][0] <= mass <= window['mw'][1]
                and window['logp'][0] <= logp <= window['logp'][1]
                and donors <= window['donors'] and acceptors <= window['acceptors']
                and rotatable <= window['rotatable'] and polar <= window['tpsa']):
            dropped['property_window'] += 1
            continue
        accessibility = sascorer.calculateScore(molecule)
        if accessibility > SYNTHETIC_ACCESSIBILITY_CUTOFF:
            dropped['synthetic_accessibility'] += 1
            continue
        if any(molecule.HasSubstructMatch(q) for q in unstable.values()):
            dropped['unstable_motif'] += 1
            continue
        rejecting, carried = split_alert_names(
            shared_alerts['names'], {h.GetDescription() for h in alerts.GetMatches(molecule)})
        if rejecting:
            dropped['structural_alert'] += 1
            continue
        # Kept, and named on the row: the reader sees that this proposal carries the same alert
        # the target's own ligands carry, rather than the alert silently disappearing.
        # Named on the row rather than folded into `extra`, which each generator fills with its
        # own fields and which the row builder reads by key.
        similarity = DataStructs.BulkTanimotoSimilarity(fingerprints.GetFingerprint(molecule), prints)
        nearest = max(range(len(similarity)), key=similarity.__getitem__)
        scaffold = Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(molecule))
        rows.append({'smiles': smiles, 'MolWt': round(mass, 1), 'LogP': round(logp, 2),
                     'TPSA': round(polar, 1), 'QED': round(QED.qed(molecule), 3),
                     'SA_score': round(accessibility, 2),
                     'nearest_retrieved': origin.get(names[nearest], names[nearest]),
                     'nearest_retrieved_smiles': names[nearest],
                     'tanimoto_to_nearest': round(similarity[nearest], 3),
                     'keeps_a_retrieved_scaffold': scaffold in seed_scaffolds,
                     'core_from': origin.get(core_source, core_source),
                     'substituent_from': origin.get(substituent_source, substituent_source),
                     'core': core, 'substituent': substituent,
                     **({'alerts_shared_with_retrieved': sorted(carried)} if carried else {}),
                     **({'transformed_from': origin.get(extra['seed'], extra['seed']),
                         'transformation': extra['transformation'],
                         'context_radius': extra['context_radius']} if extra else {})})
    rows.sort(key=lambda r: (r['tanimoto_to_nearest'], r['QED']), reverse=True)
    rows = rows[:wanted]

    embedded, embed_started = 0, time.time()
    embed_seed = int(arguments.get('seed') or EMBED_SEED)
    for row in rows:
        with_hydrogens = Chem.AddHs(Chem.MolFromSmiles(row['smiles']))
        parameters = AllChem.ETKDGv3()
        parameters.randomSeed = embed_seed
        row['embeds_3d'] = AllChem.EmbedMolecule(with_hydrogens, parameters) == 0
        row['heavy_atoms'] = Chem.MolFromSmiles(row['smiles']).GetNumHeavyAtoms()
        embedded += row['embeds_3d']

    # Preserve proposal origins and declared comparators for subsequent source-linked
    # hypothesis/function comparisons; the CSV itself makes no outcome judgment.
    import csv as _csv
    import io as _io
    parents, lines = {}, _io.StringIO()
    writer = _csv.writer(lines)
    writer.writerow(['cid', 'smiles', 'role', 'parent_cid'])
    for index, row in enumerate(rows, 1):
        proposal_id = f'proposed-{index}'
        declared = sorted({row['core_from'], row['substituent_from'], row['nearest_retrieved']})
        parents[proposal_id] = declared
        row['candidate_id'] = proposal_id
        row['declared_comparators'] = declared
        writer.writerow([proposal_id, row['smiles'], 'proposal', '|'.join(declared)])
    heavy = {row['candidate_id']: row['heavy_atoms'] for row in rows}
    for parent in sorted({p for declared in parents.values() for p in declared}):
        smiles = next((k for k, v in origin.items() if v == parent), parent)
        writer.writerow([parent, smiles, 'retrieved_parent', ''])
        molecule = seeds.get(smiles)
        if molecule is not None:
            heavy[parent] = molecule.GetNumHeavyAtoms()

    return {
        'status': 'succeeded', 'semantic_type': 'proposed_structure', 'rows': rows,
        'csv_text': lines.getvalue(), 'proposal_parents': parents,
        'heavy_atoms': heavy,
        'comparator_rule': ('제안마다 core 제공 화합물, 치환기 제공 화합물, 가장 가까운 회수 구조를 '
                            '비교 대상으로 미리 선언합니다. 결과를 본 뒤 유리한 비교 대상을 고르지 않습니다.'),
        'reason': arguments.get('reason', ''),
        'summary': {'retrieved_inputs': len(seeds), 'unparsable_inputs': len(unparsable),
                    'generator': generator_detail.get('method'),
                    'observed_cores': len(cores), 'observed_substituents': len(substituents),
                    'enumerated': len(enumerated),
                    'dropped_as_stereoisomer_of_input': stereoisomers,
                    'dropped': dropped, 'returned': len(rows), 'embeds_3d': embedded,
                    'embed_seed': embed_seed,
                    'property_window': bounds,
                    'would_have_dropped_under_generic_window': would_have_dropped_generic,
                    'similarity_saturation': similarity_saturation(rows),
                    'alerts_the_retrieved_set_carries': {
                        'names': sorted(shared_alerts['names']), 'compounds': shared_alerts['compounds'],
                        'meaning': shared_alerts['meaning']},
                    'seconds': round(time.time() - started, 1),
                    'embed_seconds': round(time.time() - embed_started, 1)},
        'method': generator_detail.get('method', 'single_cut_matched_molecular_pair_recombination'),
        'generator': generator_detail,
        'generator_error': generator_error,
        'versions': {'rdkit': rdBase.rdkitVersion,
                     'synthetic_accessibility': 'RDKit Contrib/SA_Score (Ertl & Schuffenhauer 2009)'},
        'meaning': '이 실행이 회수한 화합물들을 잘라 다시 붙인 열거 결과입니다. 활성 예측이 아니고 '
                   '표적을 보지 않았으며, 연구자가 걸러낼 가설 목록입니다.',
        'limits': LIMITS,
    }
