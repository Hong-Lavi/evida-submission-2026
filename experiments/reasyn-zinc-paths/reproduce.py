"""Reproduce the public ReaSyn/ZINC workflow with pinned author sources.

prepare downloads sources and weights, creates a separate environment, and
preprocesses public building blocks. infer requires an explicit GPU choice.
verify replays the locally generated routes; archived CSVs are never rewritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request


HERE = Path(__file__).resolve().parent
AUTHOR_COMMIT = "8a0b02178e90424266be424765b2e410dd10ab10"
TEMPLATE_COMMIT = "bef02bc4481adf3ed792090fc6169331d4d0553a"
ZINC_SHA = "96da92294b151cc7cd90d1baf055f913aa4d77d047fe80997fca06d759aad775"
TEMPLATE_SHA = "ebadaa9069eb6ec117356a6eed97bfa3a8f55f1b7e883f551e2266ead20700ab"
WEIGHTS = {
    "nv-reasyn-ar-166m-v2.ckpt": (
        "https://huggingface.co/nvidia/NV-ReaSyn-AR-166M-v2/resolve/eafc2e8ce06c532e8834fce5a991be4e7b352ed3/nv-reasyn-ar-166m-v2.ckpt",
        "1a5055c0b8eee2ca40e70f0a12047d02803173c6602413204c5a357ca8c2b65e",
    ),
    "nv-reasyn-eb-174m-v2.ckpt": (
        "https://huggingface.co/nvidia/NV-ReaSyn-EB-174M-v2/resolve/3fddcc81cae13d78f93b29898020575cae6abc6c/nv-reasyn-eb-174m-v2.ckpt",
        "fc75057a1f1f3cdd9b122532ffd34ae38d73ed7f3dfc1f6059fda7b3a4b27eeb",
    ),
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check(path: Path, expected: str) -> None:
    got = sha(path)
    if got != expected:
        raise RuntimeError(f"SHA256 mismatch: {path.name}: {got}")


def fetch(url: str, path: Path, expected: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        check(path, expected)
        return
    partial = path.with_name(path.name + ".partial")
    with urllib.request.urlopen(url, timeout=60) as source, partial.open("wb") as out:
        shutil.copyfileobj(source, out, 1 << 20)
    check(partial, expected)
    partial.rename(path)


def command(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def runtime_env(work: Path, *, gpu: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                "LOKY_MAX_CPU_COUNT": "4", "PYTHONHASHSEED": "20261011", "PYTHONDONTWRITEBYTECODE": "1"})
    env["PYTHONPATH"] = os.pathsep.join((str(work / "bootstrap"), str(work / "runtime"), str(work / "author")))
    if gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpu
    return env


def prepare(work: Path, python: str) -> None:
    work.mkdir(parents=True, exist_ok=True)
    author = work / "author"
    if not author.exists():
        command(["git", "clone", "https://github.com/NVIDIA-BioNeMo/ReaSyn.git", str(author)])
    command(["git", "checkout", AUTHOR_COMMIT], cwd=author)
    got = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=author, text=True).strip()
    assert got == AUTHOR_COMMIT
    runtime = work / "runtime"
    (runtime / "data/building_blocks").mkdir(parents=True, exist_ok=True)
    (runtime / "data/rxn_templates").mkdir(parents=True, exist_ok=True)
    (runtime / "data/processed/comp_2048").mkdir(parents=True, exist_ok=True)
    (runtime / "data/trained_model").mkdir(parents=True, exist_ok=True)
    for name in ("reasyn", "scripts"):
        link = runtime / name
        if not link.exists():
            link.symlink_to(author / name, target_is_directory=True)
    zinc = author / "data/building_blocks/building_blocks_zinc250k.txt"
    check(zinc, ZINC_SHA)
    link = runtime / "data/building_blocks/building_blocks.txt"
    if not link.exists():
        link.symlink_to(zinc)
    template = runtime / "data/rxn_templates/comprehensive.txt"
    fetch(f"https://raw.githubusercontent.com/wenhao-gao/synformer/{TEMPLATE_COMMIT}/data/rxn_templates/comprehensive.txt", template, TEMPLATE_SHA)
    config = runtime / "configs/train_ar.yml"
    config.parent.mkdir(exist_ok=True)
    if not config.exists():
        config.symlink_to(author / "configs/train_ar.yml")
    for name, (url, expected) in WEIGHTS.items():
        fetch(url, runtime / "data/trained_model" / name, expected)
    envdir = work / "env"
    if not envdir.exists():
        command([python, "-m", "venv", str(envdir)])
    pip = envdir / "bin/pip"
    command([str(pip), "install", "torch==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu118"])
    command([str(pip), "install", "-r", str(HERE / "requirements-infer.txt")])
    cache = runtime / "data/processed/comp_2048"
    fp, matrix = cache / "fpindex.pkl", cache / "matrix.pkl"
    if fp.exists() != matrix.exists():
        raise RuntimeError("Only one preprocessing cache exists; inspect before retry")
    if not fp.exists():
        command([str(envdir / "bin/python"), "scripts/preprocess.py", "--model-config", "configs/train_ar.yml"],
                cwd=runtime, env=runtime_env(work))
    validate_cache(work)


def validate_cache(work: Path) -> None:
    runtime = work / "runtime"
    check(work / "author/data/building_blocks/building_blocks_zinc250k.txt", ZINC_SHA)
    check(runtime / "data/rxn_templates/comprehensive.txt", TEMPLATE_SHA)
    code = """import pickle
from pathlib import Path
from reasyn.chem.mol import read_mol_file
root=Path('data/processed/comp_2048')
with (root/'fpindex.pkl').open('rb') as f: fp=pickle.load(f)
with (root/'matrix.pkl').open('rb') as f: mx=pickle.load(f)
source=list(read_mol_file('data/building_blocks/building_blocks.txt',show_pbar=False))
assert len(source)==len(fp.molecules)==len(mx.reactants)==37386
assert fp._fp.shape==(37386,2048) and mx.matrix.shape==(37386,115)
assert [m.smiles for m in fp.molecules]==[m.smiles for m in mx.reactants]==[m.smiles for m in source]
assert [r.smarts for r in mx.reactions]==Path('data/rxn_templates/comprehensive.txt').read_text().splitlines()
assert len(mx.seed_reaction_indices)>0
print('Public ZINC cache verified: 37386 rows, 115 ordered templates')
"""
    command([str(work / "env/bin/python"), "-c", code], cwd=runtime, env=runtime_env(work))


def infer(work: Path, gpu: str) -> None:
    validate_cache(work)
    runtime = work / "runtime"
    for name, (_, expected) in WEIGHTS.items():
        check(runtime / "data/trained_model" / name, expected)
    inspect = """import torch
from pathlib import Path
expected={'type':'morgan','morgan_radius':2,'morgan_n_bits':2048}
paths=[Path('data/trained_model/nv-reasyn-ar-166m-v2.ckpt'),Path('data/trained_model/nv-reasyn-eb-174m-v2.ckpt')]
chems=[]
for path,kind in zip(paths,('autoregressive','editflow')):
 cfg=torch.load(path,map_location='cpu',weights_only=True,mmap=True)['hyper_parameters']['config']
 assert cfg['model']['model_type']==kind
 chem=cfg['chem']; chems.append(chem)
 assert chem['fp_option']==expected
 assert chem['fpindex']=='data/processed/comp_2048/fpindex.pkl'
 assert chem['rxn_matrix']=='data/processed/comp_2048/matrix.pkl'
assert chems[0]==chems[1]
print('Official checkpoint configuration matches public ZINC cache paths')
"""
    command([str(work / "env/bin/python"), "-c", inspect], cwd=runtime, env=runtime_env(work))
    bootstrap = work / "bootstrap"
    bootstrap.mkdir(exist_ok=True)
    (bootstrap / "sitecustomize.py").write_text("import random\nimport numpy as np\nimport torch\nrandom.seed(20261011)\nnp.random.seed(20261011)\ntorch.manual_seed(20261011)\ntorch.set_num_threads(4)\n")
    inputs = list(csv.DictReader((HERE / "inputs/candidates.csv").open(newline="")))
    assert [r["candidate_id"] for r in inputs] == ["proposed-1", "proposed-2"]
    outdir = runtime / "runs"
    outdir.mkdir(exist_ok=True)
    models = ",".join(str(runtime / "data/trained_model" / name) for name in WEIGHTS)
    for row in inputs:
        ident = row["candidate_id"]
        source = runtime / f"{ident}-input.csv"
        with source.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["smiles"])
            writer.writerow([row["smiles"]])
        result = outdir / f"{ident}.csv"
        if result.exists():
            raise RuntimeError(f"Preserving existing result: {result}")
        command([str(work / "env/bin/python"), "scripts/sample.py", "-m", models,
                 "-i", str(source), "-o", str(result), "--num_gpus", "1", "--num_workers_per_gpu", "1",
                 "--num_cycles", "1", "--search_width", "4", "--exhaustiveness", "8",
                 "--time_limit", "300", "--num_editflow_samples", "100", "--num_editflow_steps", "100"],
                cwd=runtime, env=runtime_env(work, gpu=gpu))
        print(f"Completed {ident}: {result}")
    print("Run 'verify' next; generated rows may differ from the archived samples.")


def verify(work: Path) -> None:
    validate_cache(work)
    runtime = work / "runtime"
    code = """import csv,json,pickle,re
from pathlib import Path
from rdkit import Chem
from reasyn.chem.mol import Molecule,read_mol_file
from reasyn.chem.stack import Stack
root=Path('data/processed/comp_2048')
with (root/'matrix.pkl').open('rb') as f: mx=pickle.load(f)
stock={m.smiles for m in read_mol_file('data/building_blocks/building_blocks.txt',show_pbar=False)}
iso=lambda s: Chem.MolToSmiles(Chem.MolFromSmiles(s),canonical=True,isomericSmiles=True)
for ident in ('proposed-1','proposed-2'):
 p=Path('runs')/(ident+'.csv')
 rows=list(csv.DictReader(p.open(newline='')))
 good=reactive=stock_only=0
 for i,row in enumerate(rows):
  stack=Stack(); steps=0; ok=True
  for token in row['synthesis'].split(';'):
   m=re.fullmatch(r'R([0-9]+)',token)
   if m:
    idx=int(m.group(1)); steps+=1
    if idx>=len(mx.reactions) or not stack.push_rxn(mx.reactions[idx],idx): ok=False; break
   else:
    if token not in stock: ok=False; break
    stack.push_mol(Molecule(token),-1)
  ok=ok and str(steps)==row['num_steps'] and iso(row['smiles']) in {iso(m.smiles) for m in stack.get_top()}
  good+=ok; reactive+=ok and steps>0; stock_only+=ok and steps==0
 print(json.dumps({'input':ident,'rows':len(rows),'replayed':good,'reaction_routes':reactive,'stock_only':stock_only}))
 assert good==len(rows)
"""
    command([str(work / "env/bin/python"), "-c", code], cwd=runtime, env=runtime_env(work))


def archive() -> None:
    manifest = json.loads((HERE / "MANIFEST.json").read_text())
    for name, record in manifest["files"].items():
        path = HERE / name
        assert path.is_file() and path.stat().st_size == record["bytes"], name
        check(path, record["sha256"])
    for name, expected_rows in (("results/run-01-proposed-2.csv", 75),
                                ("results/run-02-proposed-1.csv", 100),
                                ("results/activity-predictions.csv", 183)):
        with (HERE / name).open(newline="") as f:
            assert len(list(csv.DictReader(f))) == expected_rows, name
    print("Archived files and all 175 raw products / 183 activity-prediction rows verified")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("archive", "prepare", "infer", "verify"))
    parser.add_argument("--work", type=Path, default=HERE / "local-reproduction")
    parser.add_argument("--python", default="python3.12")
    parser.add_argument("--gpu", help="GPU index chosen after checking local availability")
    args = parser.parse_args()
    if args.phase == "archive":
        archive()
    elif args.phase == "prepare":
        prepare(args.work.resolve(), args.python)
    elif args.phase == "infer":
        if args.gpu is None:
            parser.error("infer requires an explicit --gpu")
        infer(args.work.resolve(), args.gpu)
    else:
        verify(args.work.resolve())


if __name__ == "__main__":
    main()
