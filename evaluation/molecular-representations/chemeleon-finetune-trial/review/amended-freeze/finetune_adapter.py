"""Chemprop fine-tuning using the CheMeleon authors' public regression workflow.

Shared author settings: BondMessagePassing, mean aggregation, 256-unit regression head,
training-label standardization, validation-loss early stopping (patience 5), best checkpoint.
Adaptations: EVIDA's existing scaffold partition, one fixed seed, a matched random-init
architecture, an explicit private GPU, CSV logs and label-free prediction inputs.
"""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import time

import numpy as np
import torch
from chemprop.data import MoleculeDatapoint, MoleculeDataset, build_dataloader
from chemprop.featurizers import SimpleMoleculeMolGraphFeaturizer
from chemprop.models import MPNN
from chemprop.nn import BondMessagePassing, RegressionFFN, UnscaleTransform
from chemprop.nn.agg import MeanAggregation
from lightning import Trainer, seed_everything
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from lightning.pytorch.loggers import CSVLogger


def state_hash(state):
    digest = hashlib.sha256()
    for key, tensor in sorted(state.items()):
        digest.update(key.encode())
        digest.update(str(tuple(tensor.shape)).encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def fit_predict(train, validation, prediction_rows, checkpoint, output, *, pretrained,
                seed=20260930, epochs=50, batch_size=64):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if not torch.cuda.is_available():
        raise RuntimeError('The assigned GPU is unavailable; do not silently use another device')
    if torch.cuda.device_count() != 1:
        raise RuntimeError('Exactly one explicitly assigned GPU is required')
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    seed_everything(seed, workers=True)
    featurizer = SimpleMoleculeMolGraphFeaturizer()

    def dataset(rows, labels):
        points = [MoleculeDatapoint.from_smi(row['smiles'],
                  np.array([row['p_activity']], dtype=np.float32) if labels else None)
                  for row in rows]
        return MoleculeDataset(points, featurizer)

    training = dataset(train, True)
    valid = dataset(validation, True)
    scaler = training.normalize_targets()
    valid.normalize_targets(scaler)
    # Separate unlabelled loaders return p-activity values in their original units.
    valid_features = dataset(validation, False)
    test_features = dataset(prediction_rows, False)
    train_loader = build_dataloader(training, batch_size=batch_size, num_workers=0,
                                    shuffle=True, seed=seed, drop_last=False)
    valid_loader = build_dataloader(valid, batch_size=batch_size, num_workers=0,
                                    shuffle=False, drop_last=False)
    validation_prediction_loader = build_dataloader(valid_features, batch_size=batch_size,
                                                    num_workers=0, shuffle=False, drop_last=False)
    prediction_loader = build_dataloader(test_features, batch_size=batch_size, num_workers=0,
                                         shuffle=False, drop_last=False)
    pretraining = torch.load(checkpoint, weights_only=True, map_location='cpu')
    message_passing = BondMessagePassing(**pretraining['hyper_parameters'])
    if pretrained:
        message_passing.load_state_dict(pretraining['state_dict'], strict=True)
    initial_encoder = state_hash(message_passing.state_dict())
    predictor = RegressionFFN(input_dim=message_passing.output_dim, hidden_dim=256,
                              output_transform=UnscaleTransform.from_standard_scaler(scaler))
    initial_head = state_hash(predictor.state_dict())
    model = MPNN(message_passing, MeanAggregation(), predictor)
    checkpoint_callback = ModelCheckpoint(dirpath=output / 'checkpoint', filename='best',
                                          monitor='val_loss', mode='min', save_top_k=1,
                                          save_last=False, enable_version_counter=False)
    early = EarlyStopping(monitor='val_loss', mode='min', patience=5, verbose=False)
    trainer = Trainer(max_epochs=epochs, accelerator='gpu', devices=[0], precision='32-true',
                      deterministic=True, logger=CSVLogger(output, 'metrics'),
                      callbacks=[early, checkpoint_callback], enable_progress_bar=False,
                      enable_model_summary=False, num_sanity_val_steps=0,
                      log_every_n_steps=1, check_val_every_n_epoch=1)
    began = time.monotonic()
    trainer.fit(model, train_loader, valid_loader)
    fit_seconds = time.monotonic() - began
    best = Path(checkpoint_callback.best_model_path)
    if not best.is_file():
        raise RuntimeError('Training did not preserve a best validation checkpoint')
    # This checkpoint was just written by this Trainer in this invocation. It contains
    # Lightning metadata as well as tensors; third-party pretraining above stays weights-only.
    saved = torch.load(best, map_location='cpu', weights_only=False)
    model.load_state_dict(saved['state_dict'], strict=True)

    def predict(loader):
        batches = trainer.predict(model, loader, ckpt_path=None)
        values = torch.vstack(batches).detach().cpu().numpy().reshape(-1)
        if not np.isfinite(values).all():
            raise ValueError('Prediction contains a nonfinite value')
        return values

    validation_predictions = predict(validation_prediction_loader)
    test_predictions = predict(prediction_loader)
    if len(validation_predictions) != len(validation) or len(test_predictions) != len(prediction_rows):
        raise ValueError('Prediction row coverage changed')
    report = {'pretrained': pretrained, 'seed': seed, 'epochs_completed': trainer.current_epoch,
              'maximum_epochs': epochs, 'best_validation_loss': float(checkpoint_callback.best_model_score),
              'best_checkpoint_sha256': hashlib.sha256(best.read_bytes()).hexdigest(),
              'initial_encoder_sha256': initial_encoder,
              'fitted_encoder_sha256': state_hash(model.message_passing.state_dict()),
              'initial_head_sha256': initial_head, 'fit_seconds': fit_seconds,
              'training_rows': len(train), 'validation_rows': len(validation),
              'prediction_rows': len(prediction_rows), 'batch_size': batch_size,
              'target_scaler': {'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist()},
              'device': torch.cuda.get_device_name(0), 'GPU_used': True,
              'maximum_allocated_bytes': torch.cuda.max_memory_allocated(),
              'versions': {name: importlib.metadata.version(name)
                           for name in ('torch', 'chemprop', 'lightning', 'numpy', 'rdkit')}}
    (output / 'fit.json').write_text(json.dumps(report, indent=2))
    return validation_predictions, test_predictions, report
