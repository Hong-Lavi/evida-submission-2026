# Reproduction boundaries and commands

## Offline inspection and recalculation

Use Python 3.12 with `numpy==2.5.3` and `scipy==1.18.1` for the captured scoring environment. `verify_package.py` requires no third-party package. `recompute.py --out NEW_DIRECTORY` verifies the archive, repeats the original frozen-feature metric and 29-target-cluster bootstrap calculations, and checks agreement to `1e-12`. This is a recalculation of archived predictions, not another fit. `recompute_neural.py --out NEW_DIRECTORY` executes the unchanged neural scorer body; `recompute_independent.py --out NEW_DIRECTORY` repeats the independent SciPy/arithmetic implementation and explicitly exploratory original-policy comparison. Both check all archived fields to `1e-12`. Each destination must be new.

The neural archival wrapper binds public data paths, resolves original protocol byte identities through the source map, directs new outputs away from the archive, and uses the package verifier for retained source/prediction integrity. It does not claim to verify absent checkpoint/weight files during score-only reproduction. The independent arithmetic wrapper makes only location and original-container-identity bindings. All seven original core files remain byte-identical. Sanitized public protocol hashes are distinct from their original private-container hashes by design.

## Exact method code in a new run folder

`prepare_reproduction.py` copies data and code into a **new** folder and resolves local paths in new protocol copies. Core fitting/worker/supervisor bodies are unchanged. It records every protocol-container change; original archived protocols/receipts remain intact. Scientific task order, seed, splits, budgets, early-stopping rule, metrics and validation-only policies are retained. A new GPU identity and wall-clock deadline are necessary resource assignments, not hyperparameter changes.

The original reference predictions are included; reproducing them again is a separate RF/GP experiment. No original checkpoint, embedding array or completed output directory is copied into a new training run. Author source pins and historical originals are preserved in `source-map.json`.

Download the official checkpoint explicitly, or supply a locally retained file with the same SHA:

```bash
python -B fetch_weights.py --out downloads/chemeleon_mp.pt
python -B prepare_reproduction.py --lane frozen --weights downloads/chemeleon_mp.pt --out replay-frozen
cd replay-frozen/chemeleon-trial
python -B run_comparison.py
```

Run with the frozen-feature dependencies in `requirements-frozen.txt`. The workload is CPU-only, two concurrent task workers, two threads each, at most 1,800 seconds per task. It never opens test labels during fitting. Before original scoring, the independent gate must be rebound to the new reproduction protocol and receipts; the preparation utility records this binding. Then use:

```bash
python -B review/prescore_gate.py --score
```

For fine-tuning use `requirements-finetune.txt`, inspect available GPU resources, and explicitly assign one idle GPU. The original run uses an RTX A5000, float32, TF32 disabled, deterministic Lightning, one worker, seed 20260930, batch 64, at most 50 epochs and 1,800 seconds per arm. Neural architecture is shared: author depth-six/2,048-wide message passing, mean aggregation and 256-unit regression head. Both arms load checkpoint architecture; only the pretrained arm loads its encoder weights. Paired head initialization is checked equal. Training-only label scaling, validation-loss patience five and best checkpoint selection are shared.

```bash
python -B prepare_reproduction.py --lane finetune --weights downloads/chemeleon_mp.pt --gpu-uuid GPU_UUID --deadline 2030-01-01T00:00:00+00:00 --out replay-finetune
cd replay-finetune/chemeleon-finetune-trial
CUDA_VISIBLE_DEVICES=GPU_UUID python -B run_comparison.py --out run-01
python -B score_comparison.py
```

Replace `GPU_UUID` and the example deadline with an explicitly assigned available GPU and a real future stopping time. The script checks that exact assignment and does not switch devices or retry failed tasks. It retains all 60 planned arm receipts, including resource/time skips. Scoring verifies the full completion list and all prediction identities before opening official labels. Full refitting has not been executed while assembling this portable package; portability checks cover code identity, file layout, path/pin resolution and archived metric recalculation.

## Chronology and retained failures

The frozen-feature protocol precedes its task fits. An independent scoring amendment precedes reading follow-up labels; it strengthens the global receipt/identity/coverage gate without changing fits, metrics or selection rules. Existing RF/GP results on this benchmark were already known.

The neural synthetic health check initially failed at checkpoint handling; that original failure and the separate successful synthetic check remain under `chemeleon-finetune-trial/preflight-01` and `preflight-02`. They are not benchmark tasks. Independent review then found a missing math import and a singleton trailing-batch coverage problem before benchmark neural training. Original freeze, pretraining amendment and amended freeze are all retained. `drop_last=False`, protocol-hash checks and complete resource-stop receipts were fixed before the current benchmark run. No benchmark outcome was used for those repairs.

All 60 terminal neural records were appended after the coordinator completed the original scorer and independent review. There are zero failed/skipped neural benchmark arms. The independent pre-score gate record and post-score recalculation are included under `review-neural-01/`. Individual checkpoint hashes, raw predictions, fit metadata and logs are retained without exporting checkpoint files. The exploratory original-versus-expanded policy comparison is separate from the frozen primary.

For newly generated fits, run an independent terminal-receipt/mean-baseline gate before first scoring; the included historical `review-neural-01/pre_score_gate.py` is bound to the original protocol digest and must not be presented as directly accepting a new run. Its rule checks can be reused with an explicitly reviewed new-protocol binding. The original scorer itself remains unchanged.
