"""Smoke-check actual author weights and batched fingerprint invariance on CPU."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import torch
from encoder_adapter import LocalCheMeleonFingerprint

HERE = Path(__file__).resolve().parent
torch.set_num_threads(2)
torch.manual_seed(20260930)
checkpoint = HERE / "weights/chemeleon_mp.pt"
expected = json.loads((HERE / "weights-receipt.json").read_text())["sha256"]
assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == expected
began = time.monotonic()
encoder = LocalCheMeleonFingerprint(checkpoint)
molecules = ["C", "CC", "CCC", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"]
one_batch = encoder.batches(molecules, batch_size=5)
separate = encoder.batches(molecules, batch_size=1)
assert one_batch.shape[0] == 5
np.testing.assert_allclose(one_batch, separate, rtol=1e-4, atol=1e-5)
assert not np.allclose(one_batch[0], one_batch[1])
repeated = encoder.batches(molecules * 20, batch_size=64)
np.testing.assert_allclose(repeated[:5], one_batch, rtol=1e-4, atol=1e-5)
result = {
    "status": "passed", "at_utc": datetime.now(timezone.utc).isoformat(),
    "author_commit": subprocess.check_output(["git", "-C", str(HERE / "author"), "rev-parse", "HEAD"], text=True).strip(),
    "weights_sha256": expected, "shape": list(one_batch.shape), "device": "cpu",
    "maximum_batch_difference": float(np.abs(one_batch - separate).max()),
    "seconds": time.monotonic() - began, "official_test_labels_read": False,
    "dependencies": {name: version(name) for name in ["torch", "chemprop", "lightning", "rdkit", "numpy", "scikit-learn"]},
}
with (HERE / "preflight-result.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps(result))
