# Contrainte CPU uniquement — exclusion des architectures deep learning gourmandes

Toutes les architectures nécessitant un GPU sont hors périmètre : ConvLSTM, Graph Attention Network (GAT-LSTM), Temporal Fusion Transformer complet, et modèles SITS (LTAE, TSViT). Le modèle doit être entraînable et déployable sur CPU standard, sans infrastructure cloud spécialisée. Cette contrainte reflète la réalité opérationnelle du CNA/IFVM à Madagascar : ressources informatiques limitées, dépendance réduite aux financements extérieurs pour l'infrastructure, et reproductibilité garantie dans le contexte institutionnel local.

## Alternatives considérées

- **GAT-LSTM (Graph Attention Network + LSTM)** — rejeté malgré sa pertinence biologique (modélisation de la propagation spatiale entre régions adjacentes) : requiert GPU pour un entraînement en temps raisonnable.
- **Temporal Fusion Transformer (TFT)** — rejeté malgré ses capacités multi-horizon natives : trop lent sur CPU pour des cycles d'entraînement acceptables.
- **ConvLSTM** — rejeté : inadapté aux données polygonales (régions naturelles) sans rasterisation coûteuse, et GPU-dépendant.

## Stack retenue

- Phase 1 : LightGBM / XGBoost (baseline, CPU natif, rapide)
- Phase 2 : NeuralProphet (multi-horizon, CPU natif, gère les lacunes)
- Phase 3 (optionnelle) : LSTM léger PyTorch sur CPU si AUC < 0,80 après phases 1–2

## Conséquences

- La dépendance spatiale entre régions naturelles adjacentes n'est pas modélisée structurellement — elle est partiellement capturée via des features de lag spatial (valeurs des régions voisines) ajoutées manuellement en feature engineering.
- Si des ressources GPU deviennent disponibles, GAT-LSTM est l'architecture prioritaire à évaluer en premier.
