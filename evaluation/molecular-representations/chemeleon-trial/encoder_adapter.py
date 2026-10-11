"""Run the authors' frozen CheMeleon fingerprint with an explicit local checkpoint.

The message-passing construction and fingerprint call are the author's MIT code.
Only checkpoint location/loading device and batch iteration are adapted here.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "author"))
from chemeleon_fingerprint import CheMeleonFingerprint
from chemprop import featurizers, nn
from chemprop.models import MPNN
from chemprop.nn import RegressionFFN
import numpy as np
import torch


class LocalCheMeleonFingerprint(CheMeleonFingerprint):
    def __init__(self, checkpoint, device="cpu"):
        self.featurizer = featurizers.SimpleMoleculeMolGraphFeaturizer()
        checkpoint_data = torch.load(checkpoint, weights_only=True, map_location="cpu")
        message_passing = nn.BondMessagePassing(**checkpoint_data["hyper_parameters"])
        message_passing.load_state_dict(checkpoint_data["state_dict"])
        self.model = MPNN(
            message_passing=message_passing,
            agg=nn.MeanAggregation(),
            predictor=RegressionFFN(input_dim=message_passing.output_dim),
        )
        self.model.eval()
        self.model.to(device=device)

    def batches(self, molecules, batch_size=64):
        parts = [self(molecules[i:i + batch_size]) for i in range(0, len(molecules), batch_size)]
        values = np.concatenate(parts)
        if not np.isfinite(values).all():
            raise ValueError("Non-finite author fingerprint; preserve the failed case")
        return values
