---
Status: done
---

# #02 — Reconstruction du niveau de grégarité et du potentiel acridien

## What to build

À partir du DataFrame de relevés acridiens géoréférencés, calculer pour chaque ligne le niveau de grégarité simplifié (S/St/T/G) depuis les comptages `Sol`, `Trans`, `Greg`, puis la densité totale équivalent imago, puis le potentiel acridien (0–5) via la matrice Annexe 8 du Manuel de lutte préventive. La logique de classification est la suivante (issue d'un prototype) :

```python
# Niveau de grégarité simplifié
total = Sol + Trans + Greg
if total == 0:       niveau = "absent"
elif Greg > 0:       niveau = "G"
elif Trans >= Sol > 0: niveau = "T"   # mappé T1 (conservateur) dans Annexe 8
elif Trans > 0:      niveau = "St"
else:                niveau = "S"

# Densité équivalent imago (ind/ha)
densite = DI_dif_moy + DL_dif_moy / 9
```

T est mappé sur T1 (valeur conservatrice) car les sous-niveaux T1/T2/T3 ne sont pas distingués dans les relevés terrain. La sortie enrichit le DataFrame relevé avec les colonnes `niveau_gregarite`, `densite_imago`, `potentiel_acridien`.

## Acceptance criteria

- [x] Les cinq cas (absent, S, St, T, G) sont correctement classifiés
- [x] T est systématiquement mappé sur T1 dans la matrice Annexe 8
- [x] La formule de densité (DI + DL/9) est correctement appliquée
- [x] Tests unitaires couvrant chaque case de la matrice Annexe 8 avec des valeurs attendues tirées du Manuel

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/01-nettoyage-jointure-relevés.md`
