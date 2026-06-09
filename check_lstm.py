"""Vérif isolée du LSTM torch — doit afficher 'lstm OK ...' rapidement."""
import sys
sys.path.insert(0, "src")

import numpy as np
from lstm_ordinal import LSTMOrdinalRegressor

X = np.random.randn(200, 5)
y = (np.random.rand(200) * 4).astype(int)

print("Entraînement LSTM (30 epochs)…", flush=True)
m = LSTMOrdinalRegressor(epochs=30).fit(X, y)
print("lstm OK — prédictions échantillon :", m.predict(X[:5]), flush=True)
