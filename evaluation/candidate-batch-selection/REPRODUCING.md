# Reproduction boundaries

## Offline result checks

`verify_package.py` needs Python standard library. `recompute.py` additionally needs NumPy2.5.3. Both use only packaged files. The first checks exported hashes, original scientific byte identity where unchanged, source records, all30 posterior hashes, and every label's source CSV identity. The second verifies both complete3600-row selection archives, independently recalculates every scientific metric and all paired intervals, and confirms both versions' full numerical results agree within1e-12.

The archive preserves all actual runtime receipts and diagnostics for 30 tasks and 3,600 selection rows per version. Synthetic failure fixtures have their own declared denominators and are never added to the scientific task count. Protocol and receipt hashes in historical files refer to original bytes. Path/session redactions are mapped explicitly; `source-map.json` carries both original and public hashes.

## CPU selection replay from the supplied posterior

No network, trained-weight download, fitting, API key, provider, or GPU is required. Install the pinned NumPy requirement into a new environment, then prepare a new directory:

```bash
.venv/bin/python -B prepare_replay.py --attempt acquisition-02 --out /absolute/new/replay-directory
```

The directory must not exist. Preparation copies the original `acquisition.py`, `common.py`, `selection_worker.py`, `run_selection.py`, and `score_selection.py` bytes without changing function bodies. It binds packet/posterior/gold paths to the local packaged files and creates new integrity pins/receipt. Every scientific configuration field remains fixed. `verification/portable-preparation.json` records successful preparation and active-pin verification, with **no selection execution during packaging**.

From that new directory, using the absolute path to the installed Python interpreter:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 /absolute/path/to/.venv/bin/python -B run_selection.py
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 /absolute/path/to/.venv/bin/python -B score_selection.py
```

The second command is a separate phase and must follow the complete selection seal. The unchanged scorer enforces its full structural/hash gate before opening labels. Each task has one CPU worker, two threads,180seconds wall time and180/181 CPU seconds, and2GiB address-space limit; there is no automatic retry. Resource-limit behavior requires a POSIX environment. Use `--attempt acquisition-01` only to inspect the preserved original numerical behavior; acquisition-02 guarantees the intended equality invariant.

A fresh replay can vary with CPU/BLAS accumulation and NumPy implementation. Preserve all outputs/failures; do not replace the archived outcomes with a favorable rerun. Exact equality groups are repaired in02, but cross-platform bitwise equality for every nonduplicate sample is not promised. The public metrics were recomputed from provided selections; a new complete public replay was **not** executed while building this package.

## Posterior and model boundary

All30 original compressed NPZ posteriors are included byte-for-byte, about32MB total, largest4.12MB. No manifest-only substitute or network reconstruction is needed for the commands above. Arrays include candidate IDs, posterior mean, latent covariance, and observation SD. Original reconstruction receipts expose the saved-model marginal agreement (absolute1e-7 on mean/latent SD/observation SD), no-refit provenance, and software versions.

The model-reference directory retains saved GP parameters, original RF/GP predictions and policy choices. `provenance/reconstruct_gp.py` and `run_reconstruction.py` preserve the original recovery code for audit, but require their historical project layout and model dependencies; they are not advertised as a runnable public reconstruction entrypoint. For a separate original-model refit/reconstruction study, use the adjacent [conditional-activity-models](../conditional-activity-models/README.md) package, its data preparation, author-code notice and model pins, then validate marginal agreement before a new acquisition experiment. Such model work is outside this package's executed reproduction claim.

## Failures and repairs remain inspectable

Version01 includes the original truncated-output finding, preserved revisions, actual SIGKILL synthetic recovery fixtures, and every source/input mutation check. Version02 includes its numerical amendment,110-group prefreeze check,20 passing tests, one actual selection run, and selection-only comparison before its final scorer. Setup executable/path mistakes are retained separately and produced no scientific response, score, or extra selection attempt. Unlicensed qPO source itself is excluded; its hash in historical protocol metadata is not a claim that it is available in this distribution.
