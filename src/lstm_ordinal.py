"""LSTM ordinal (torch) — modèle « testé » du benchmark #07.

Régressseur séquentiel minimal, à interface sklearn (`fit`/`predict`), produisant
un score continu de sévérité-phase arrondi en aval par `to_ordinal`. Le PRD §17
demande de **tester** un LSTM sans l'imposer ; ce wrapper fournit donc une
implémentation compacte et honnête, sans prétention d'optimisation.

Limite assumée : faute d'index temporel passé à `run_benchmark`, chaque ligne est
traitée comme une séquence de longueur 1 (LSTM dégénéré ≈ MLP récurrent). À
enrichir si l'on injecte des séquences cellule × décades successives.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn


class _Net(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):  # x : (batch, seq=1, n_features)
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


class LSTMOrdinalRegressor:
    """Régressseur LSTM minimal compatible sklearn (fit/predict, score continu)."""

    def __init__(self, hidden: int = 32, epochs: int = 30, lr: float = 0.01,
                 random_state: int = 42):
        self.hidden = hidden
        self.epochs = epochs
        self.lr = lr
        self.random_state = random_state

    def fit(self, X, y, sample_weight=None):
        torch.manual_seed(self.random_state)
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.float32)
        self._mu = X.mean(axis=0)
        self._sd = X.std(axis=0) + 1e-8
        Xn = (X - self._mu) / self._sd

        xt = torch.tensor(Xn).unsqueeze(1)            # (n, seq=1, n_features)
        yt = torch.tensor(y)
        wt = (torch.tensor(np.asarray(sample_weight, dtype=np.float32))
              if sample_weight is not None else torch.ones_like(yt))

        self.net = _Net(X.shape[1], self.hidden)
        opt = torch.optim.Adam(self.net.parameters(), lr=self.lr)
        self.net.train()
        for _ in range(self.epochs):
            opt.zero_grad()
            pred = self.net(xt)
            loss = (wt * (pred - yt) ** 2).mean()      # MSE pondérée par classe
            loss.backward()
            opt.step()
        return self

    def predict(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        Xn = (X - self._mu) / self._sd
        xt = torch.tensor(Xn).unsqueeze(1)
        self.net.eval()
        with torch.no_grad():
            return self.net(xt).numpy()
