"""Local packaging utility; reads sibling trials, writes only this package.
No fitting, scoring, provider, GPU or network calls. Fine-tune results are excluded
until the coordinator explicitly authorizes terminal-result packaging.
"""
from pathlib import Path
import ast
import hashlib
import json
import re

def canonical_ast(node):
    if isinstance(node, ast.AST):
        return [type(node).__name__, [[key, canonical_ast(value)] for key, value in ast.iter_fields(node) if value is not None and value != []]]
    if isinstance(node, list):return [canonical_ast(value) for value in node]
    return node

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[1]
sha = lambda raw: hashlib.sha256(raw).hexdigest()
records = []

def sanitize(text):
    replacements = [(str(BASE), '<experiment-root>'), (str(REPO), '<research-root>')]
    for source, target in replacements:
        text = text.replace(source, target)
    text = re.sub(r'/data/user_home/[^/\s\"\']+', '<user-home>', text)
    text = re.sub(r'GPU-[0-9a-fA-F-]{36}', '<assigned-gpu-uuid>', text)
    return text

def copy(source, dest=None):
    source = Path(source)
    dest = HERE / (dest or source.relative_to(BASE))
    raw = source.read_bytes()
    try:
        public = sanitize(raw.decode()).encode()
    except UnicodeDecodeError:
        public = raw
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(public)
    records.append({'original_logical_name': str(source.relative_to(BASE)),
                    'public_path': str(dest.relative_to(HERE)),
                    'original_sha256': sha(raw), 'public_sha256': sha(public),
                    'transformation': 'unchanged' if raw == public else 'workstation paths/GPU identifier replaced; scientific content retained'})

def write(name, value):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def function_hashes(path):
    tree=ast.parse(path.read_text())
    return {n.name:sha(json.dumps(canonical_ast(n),ensure_ascii=False,separators=(',', ':')).encode())
            for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}

if __name__ == '__main__':
    status=HERE/'finetune-status.json'
    if status.exists() and json.loads(status.read_text()).get('results_included'):
        raise RuntimeError('Preserve appended terminal archive; do not rebuild the preparation snapshot')
    for lane in ['chemeleon-trial','chemeleon-finetune-trial']:
        src=BASE/lane
        for p in sorted(src.glob('*.py')): copy(p)
        for name in ['protocol.json','protocol-receipt.json','preflight-result.json','input-manifest.json','metric-source-map.json','pretraining-amendment.json']:
            if (src/name).is_file():copy(src/name)
        for p in sorted((src/'review').rglob('*')):
            if p.is_file() and p.suffix in ['.json','.py','.md'] and '__pycache__' not in p.parts and 'scoring-gate-fixtures' not in p.parts:
                copy(p)
    for sub in ['preflight-01','preflight-02']:
        for p in sorted((BASE/'chemeleon-finetune-trial'/sub).rglob('*.json')):copy(p)
        log=BASE/'chemeleon-finetune-trial'/(sub+'.log')
        if log.exists():copy(log)
    for p in sorted((BASE/'chemeleon-finetune-trial/inputs').glob('*.json')):copy(p)
    for p in sorted((BASE/'gp-public-package/data').rglob('*')):
        if p.is_file():copy(p,Path('data')/p.relative_to(BASE/'gp-public-package/data'))
    for p in sorted((BASE/'tanimoto-trial/frozen-product').rglob('*.py')):copy(p)
    copy(BASE/'tanimoto-trial/protocol.json')
    for p in sorted((BASE/'tanimoto-trial/run-01').glob('*/predictions.json')):copy(p)
    for p in sorted((BASE/'chemeleon-trial/run-01').rglob('*')):
        if p.is_file() and p.suffix in ['.json','.log']:
            copy(p)
    author=BASE/'chemeleon-trial/author'
    for name in ['LICENSE','README.md','chemeleon_fingerprint.py','models/chemprop_mpnn/evaluate.py','analysis/fine-tuning/scripts/finetune.py']:
        copy(author/name)
    copy(BASE/'gp-public-package/licenses/MoleculeACE-LICENCE.txt','licenses/MoleculeACE-LICENCE.txt')
    copy(author/'LICENSE','licenses/CheMeleon-MIT.txt')
    copy(BASE/'gp-public-package/dataset-pins.json','dataset-pins.json')
    record=json.loads((BASE/'chemeleon-trial/zenodo-record-15460715.json').read_text())
    write('weights.json',{'repository':'https://github.com/JacksonBurns/chemeleon','author_commit':'b5e5bd88a7070c3f278e7e65e85b792617bf125c','record':'https://zenodo.org/records/15460715','doi':record['doi'],'license':record['metadata']['license'],'filename':'chemeleon_mp.pt','size_bytes':record['files'][0]['size'],'download_url':record['files'][0]['links']['self'],'sha256':'c376624d3407204e780a0ed13a9ac097cc9bb1c13ef89cdbc633c1715c183651','included':False})
    parity=[]
    for lane,names in [('chemeleon-trial',['encoder_adapter.py','run_comparison.py','score_comparison.py']),('chemeleon-finetune-trial',['finetune_adapter.py','run_comparison.py','score_comparison.py','metrics_common.py'])]:
        for name in names:
            original=BASE/lane/name;public=HERE/lane/name
            a,b=function_hashes(original),function_hashes(public)
            assert a==b
            parity.append({'source':str(Path(lane)/name),'original_file_sha256':sha(original.read_bytes()),'public_file_sha256':sha(public.read_bytes()),'function_ast_sha256':a,'all_top_level_function_and_class_bodies_identical':True})
    write('provenance/portable-source-check.json',{'status':'PASS','adaptation':'No core body changes; prepare_reproduction.py supplies portable paths and explicit resource settings in a NEW reproduction tree. Historical sanitized protocol remains separate.','files':parity})
    write('source-map.json',{'description':'Original byte identities retained even where workstation paths/GPU identifiers are sanitized. Raw predictions and fitting function bodies unchanged. Original protocol receipts point to original identities, not sanitized public bytes.','files':records})
    write('finetune-status.json',{'status':'AWAITING_COORDINATOR_TERMINAL_SCORING_AND_UNSEAL','planned_tasks':30,'planned_neural_arms':60,'results_included':False,'note':'No benchmark neural outcomes are read, scored or reported by this preparation. All terminal arms/failures will be appended after explicit coordinator review.'})
    print(json.dumps({'copied_files':len(records),'core_files_checked':len(parity),'fine_tune_results_included':False}))
