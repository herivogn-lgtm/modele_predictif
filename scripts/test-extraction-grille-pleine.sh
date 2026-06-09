#!/bin/bash
# Script de test — Extraction grille pleine (échantillon)
# À exécuter manuellement pour valider le workflow avant production

set -e  # Arrêter en cas d'erreur

VENV="./.venv/bin/python"
MONTH="2026-06"

echo "=== TEST EXTRACTION GRILLE PLEINE (échantillon) ==="
echo ""
echo "Mode: --month $MONTH --buffer 2"
echo "Cellules: all (181 413)"
echo ""

# Afficher la simulation sans exécuter
echo "1. Simulation (dry-run) :"
$VENV -c "
import sys
sys.path.insert(0, 'src')
from extraction_gee_helpers import parse_month_to_decades, build_decade_calendar_range
from config_gee import POINT_EXPORT_TILE

month_str = '$MONTH'
buffer = 2
decade_range = parse_month_to_decades(month_str, buffer=buffer)
y_start, d_start, y_end, d_end = decade_range
calendar = build_decade_calendar_range(y_start, d_start, y_end, d_end)

total_cells = 181413
tiles = (total_cells + POINT_EXPORT_TILE - 1) // POINT_EXPORT_TILE
sources = 3
batches = 1
dynamic_tasks = sources * batches * tiles

print(f'   Plage : décades {y_start}-{d_start} à {y_end}-{d_end}')
print(f'   Décades : {len(calendar)}')
print(f'   Tuiles : {tiles}')
print(f'   Tâches GEE : {dynamic_tasks}')
print(f'   Lignes attendues : {total_cells * len(calendar):,}')
"

echo ""
read -p "Continuer avec l'extraction réelle ? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Annulé."
    exit 0
fi

echo ""
echo "2. Lancement des tâches GEE (submit) :"
$VENV src/04b_export_variables_gee.py submit \
  --cells all \
  --month $MONTH \
  --no-baseline

echo ""
echo "3. Suivi des tâches (status) :"
echo "   Exécuter manuellement :"
echo "   $VENV src/04b_export_variables_gee.py status"
echo ""
echo "4. Téléchargement CSV :"
echo "   - Aller sur Google Drive : https://drive.google.com"
echo "   - Dossier : ee_exports_locusta_v04/"
echo "   - Télécharger tous les CSV v04_*_y2026_t*.csv"
echo "   - Déplacer dans : data/processed/04_exports_drive/"
echo ""
echo "5. Assemblage (après téléchargement) :"
echo "   $VENV src/04b_export_variables_gee.py assemble --cells all --month $MONTH"
echo ""
echo "6. Pipeline complet :"
echo "   $VENV src/feature_engineering_05.py"
echo "   $VENV src/construction_table_06.py"
echo "   $VENV src/sorties_operationnelles_09.py --campagne 2025-2026 --decade 18"
echo ""
echo "✓ Tâches lancées — Voir runbook pour la suite"
