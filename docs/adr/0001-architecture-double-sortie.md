# Architecture double sortie : niveau de risque opérationnel + modèle hiérarchique analytique

Le modèle produit deux types de sorties en parallèle : (1) un niveau de risque acridien 0–4 par région naturelle et par période, utilisé directement par les équipes CNA/IFVM pour programmer les prospections, et (2) un modèle hiérarchique à trois étapes (présence/absence → densité → phase dominante) destiné à l'analyse scientifique et à la validation. On a choisi cette architecture plutôt qu'une sortie unique car les deux usages ont des métriques, des audiences et des cycles de décision incompatibles : le niveau de risque 0–4 est cohérent avec le SIG-LMC existant du CNA et directement actionnable sur le terrain, tandis que les composantes séparées permettent la publication scientifique et l'interprétation des mécanismes.

## Alternatives considérées

- **Sortie unique (niveau de risque 0–4 seulement)** — rejeté car empêche l'analyse fine des déterminants biologiques (densité, phase) nécessaire à la thèse.
- **Sortie unique (modèle hiérarchique seulement)** — rejeté car le niveau de risque 0–4 doit être re-calculé manuellement à chaque usage opérationnel, introduisant des erreurs de transcription.

## Conséquences

- Le niveau de risque 0–4 est reconstruit depuis les données terrain (Sol, Trans, Greg, densité) via la matrice Annexe 8 du Manuel de lutte préventive (Duranton et al., 2009) avec simplification S/St/T/G (les sous-niveaux T1/T2/T3 ne sont pas distingués sur le terrain).
- Le potentiel écologique (second facteur de la matrice) est appris implicitement par le modèle depuis les features GEE — il n'est pas reconstruit séparément.
