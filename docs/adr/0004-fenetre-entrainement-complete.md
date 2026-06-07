---
status: accepted
---

# Fenêtre d'entraînement = span complet 2001–2026 (ne pas couper les années précoces)

## Contexte

La thèse hésite (§31 : 2001–2025 ; §33 : 2005–2025). Les relevés sont épars avant 2012
et abondants ensuite, avec une **lacune totale en 2023–2024** (zéro relevé), 2025 partiel,
2026 riche. Tentation naturelle : restreindre aux années récentes « propres ».

Or la classe critique — **grégaire (niveau 3, 6,6 %, 1 947 cas)** — est répartie sur
**toute** la période ; les années précoces 2004/2007/2008 concentrent ~570 cas (~29 % du
total grégaire). Balance globale 0–3 : 31 / 37 / 26 / 7 %.

## Décision

- **Fenêtre = tout le span étiqueté 2001–2026.** Ne pas couper les années précoces :
  elles portent une part majeure des rares exemples grégaires.
- **Rejet du 2005–2025** (thèse §33) : perdrait 2002–2004.
- **Lacune 2023–2024** : les covariables (NDVI/LST/CHIRPS) restent **continues côté GEE**,
  seuls les labels manquent → on **saute** ces campagnes en validation, sans casser le
  calcul des features.
- **Validation walk-forward par campagne** (chronologique), cohérente avec le forecast
  T+1 (ADR 0002).

## Conséquences

- Biais d'effort de prospection (plus de relevés récents) assumé : il affecte
  l'échantillonnage, pas le label conditionnel (« sachant qu'on a prospecté, quelle phase »).
- Le niveau 3 minoritaire impose une **pondération de classe** / un réglage de seuil en aval.
