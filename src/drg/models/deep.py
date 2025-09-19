"""Deep-learning forecaster (optional extended analysis).

A stacked LSTM (or GRU) sequence-to-one regressor over the last
``sequence_length`` half-hourly steps of demand plus the exogenous drivers.
Torch is an optional dependency: if it is not installed the trainer reports
that cleanly and the pipeline continues with the tree/linear models.

Sequences never cross a neighbourhood boundary, and standardisation
statistics are fitted on the training window only, so there is no leakage
either across sites or across time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

try:  # pragma: no cover - import guard
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = object  # type: ignore[assignment]
    TORCH_AVAILABLE = False


@dataclass
class LSTMParams:
    sequence_length: int = 96
    hidden_size: int = 96
    num_layers: int = 2
    dropout: float = 0.15
    epochs: int = 25
    batch_size: int = 128
    learning_rate: float = 1e-3
    patience: int = 5
    cell: str = "lstm"  # lstm | gru
    seed: int = 42


def _build_sequences(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    seq_len: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (X[n, seq_len, f], y[n], row_index[n]) without crossing sites."""
    xs, ys, idx = [], [], []
    df = df.sort_values(["neighbourhood_id", "timestamp"])
    for _, sub in df.groupby("neighbourhood_id", observed=True, sort=False):
        values = sub[feature_cols].to_numpy(dtype=np.float32)
        target = sub[target_col].to_numpy(dtype=np.float32)
        positions = sub.index.to_numpy()
        if len(sub) <= seq_len:
            continue
        # strided view over the contiguous per-site block
        n_windows = len(sub) - seq_len + 1
        strided = np.lib.stride_tricks.sliding_window_view(values, seq_len, axis=0)
        strided = np.transpose(strided, (0, 2, 1))[:n_windows]
        xs.append(strided)
        ys.append(target[seq_len - 1 :])
        idx.append(positions[seq_len - 1 :])
    if not xs:
        return np.empty((0, seq_len, len(feature_cols)), np.float32), np.empty(0), np.empty(0, int)
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(idx)


if TORCH_AVAILABLE:

    class _SequenceNet(nn.Module):
        def __init__(self, n_features: int, params: LSTMParams) -> None:
            super().__init__()
            cell = nn.GRU if params.cell.lower() == "gru" else nn.LSTM
            self.rnn = cell(
                input_size=n_features,
                hidden_size=params.hidden_size,
                num_layers=params.num_layers,
                batch_first=True,
                dropout=params.dropout if params.num_layers > 1 else 0.0,
            )
            self.head = nn.Sequential(
                nn.LayerNorm(params.hidden_size),
                nn.Linear(params.hidden_size, params.hidden_size // 2),
                nn.ReLU(),
                nn.Dropout(params.dropout),
                nn.Linear(params.hidden_size // 2, 1),
            )

        def forward(self, x):  # noqa: D102
            out, _ = self.rnn(x)
            return self.head(out[:, -1, :]).squeeze(-1)

else:  # pragma: no cover
    _SequenceNet = None  # type: ignore[assignment]


class LSTMForecaster:
    """Sequence forecaster with a scikit-learn-like interface."""

    name = "lstm"

    def __init__(self, **kwargs: Any) -> None:
        known = {f.name for f in LSTMParams.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        self.params = LSTMParams(**{k: v for k, v in kwargs.items() if k in known})
        self.feature_columns: list[str] = []
        self.model: Any = None
        self.x_mean: np.ndarray | None = None
        self.x_std: np.ndarray | None = None
        self.y_mean: float = 0.0
        self.y_std: float = 1.0
        self.history: list[dict[str, float]] = []

    # ------------------------------------------------------------------ fit
    def fit(
        self,
        train: pd.DataFrame,
        feature_cols: list[str],
        target_col: str,
        val: pd.DataFrame | None = None,
    ) -> "LSTMForecaster":
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is not installed. Install the deep extra:\n"
                "    pip install -r requirements-deep.txt"
            )
        torch.manual_seed(self.params.seed)
        np.random.seed(self.params.seed)

        self.feature_columns = list(feature_cols)
        train = train.reset_index(drop=True)
        Xtr, ytr, _ = _build_sequences(train, feature_cols, target_col, self.params.sequence_length)
        if Xtr.size == 0:
            raise ValueError("Not enough history to build LSTM training sequences")

        self.x_mean = np.nan_to_num(Xtr.reshape(-1, Xtr.shape[-1]).mean(axis=0))
        self.x_std = np.nan_to_num(Xtr.reshape(-1, Xtr.shape[-1]).std(axis=0))
        self.x_std[self.x_std < 1e-8] = 1.0
        self.y_mean, self.y_std = float(ytr.mean()), float(ytr.std() or 1.0)

        Xtr_s = self._scale_x(Xtr)
        ytr_s = (ytr - self.y_mean) / self.y_std

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = _SequenceNet(Xtr.shape[-1], self.params).to(device)
        optimiser = torch.optim.AdamW(self.model.parameters(), lr=self.params.learning_rate)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimiser, patience=2, factor=0.5)
        loss_fn = nn.HuberLoss(delta=1.0)

        loader = DataLoader(
            TensorDataset(torch.from_numpy(Xtr_s), torch.from_numpy(ytr_s.astype(np.float32))),
            batch_size=self.params.batch_size,
            shuffle=True,
            drop_last=False,
        )

        val_tensors = None
        if val is not None and len(val):
            Xv, yv, _ = _build_sequences(
                val.reset_index(drop=True), feature_cols, target_col, self.params.sequence_length
            )
            if Xv.size:
                val_tensors = (
                    torch.from_numpy(self._scale_x(Xv)).to(device),
                    torch.from_numpy(((yv - self.y_mean) / self.y_std).astype(np.float32)).to(device),
                )

        best_loss, best_state, bad_epochs = float("inf"), None, 0
        for epoch in range(1, self.params.epochs + 1):
            self.model.train()
            running = 0.0
            for xb, yb in loader:
                xb, yb = xb.to(device), yb.to(device)
                optimiser.zero_grad()
                loss = loss_fn(self.model(xb), yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimiser.step()
                running += float(loss) * len(xb)
            train_loss = running / len(loader.dataset)

            if val_tensors is not None:
                self.model.eval()
                with torch.no_grad():
                    val_loss = float(loss_fn(self.model(val_tensors[0]), val_tensors[1]))
            else:
                val_loss = train_loss

            scheduler.step(val_loss)
            self.history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
            log.info(
                "lstm epoch %02d/%02d  train=%.5f  val=%.5f", epoch, self.params.epochs, train_loss, val_loss
            )

            if val_loss < best_loss - 1e-5:
                best_loss, bad_epochs = val_loss, 0
                best_state = {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()}
            else:
                bad_epochs += 1
                if bad_epochs >= self.params.patience:
                    log.info("early stopping at epoch %s", epoch)
                    break

        if best_state is not None:
            self.model.load_state_dict(best_state)
        self.model.eval()
        return self

    def _scale_x(self, X: np.ndarray) -> np.ndarray:
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return ((X - self.x_mean) / self.x_std).astype(np.float32)

    # -------------------------------------------------------------- predict
    def predict(self, df: pd.DataFrame, target_col: str = "demand_kwh") -> np.ndarray:
        """Predict for every row; warm-up rows fall back to the last observation."""
        if self.model is None:
            raise RuntimeError("LSTMForecaster has not been fitted")
        frame = df.reset_index(drop=True)
        X, _, idx = _build_sequences(frame, self.feature_columns, target_col, self.params.sequence_length)
        preds = np.full(len(frame), np.nan)
        if X.size:
            device = next(self.model.parameters()).device
            with torch.no_grad():
                batched = []
                tensor = torch.from_numpy(self._scale_x(X))
                for start in range(0, len(tensor), 2048):
                    chunk = tensor[start : start + 2048].to(device)
                    batched.append(self.model(chunk).cpu().numpy())
            out = np.concatenate(batched) * self.y_std + self.y_mean
            preds[idx.astype(int)] = out
        fallback = frame["lag_1"] if "lag_1" in frame.columns else frame.get(target_col)
        if fallback is not None:
            preds = np.where(np.isnan(preds), np.asarray(fallback, dtype=float), preds)
        return np.clip(preds, 0.0, None)

    # ------------------------------------------------------------ artefacts
    def _state_dict(self) -> dict[str, Any]:
        return {
            "params": self.params.__dict__,
            "feature_columns": self.feature_columns,
            "x_mean": self.x_mean,
            "x_std": self.x_std,
            "y_mean": self.y_mean,
            "y_std": self.y_std,
            "weights": (
                {k: v.cpu().numpy() for k, v in self.model.state_dict().items()}
                if self.model is not None
                else {}
            ),
            "history": self.history,
        }
