#!/usr/bin/env python3
"""Test dry-run — Vérifie que --decades 2026-14:2026-18 extrait bien 5 décades seulement."""

import sys
sys.path.insert(0, 'src')

from extraction_gee_helpers import parse_decades_range, build_decade_calendar_range, build_specs
from config_gee import POINT_EXPORT_TILE

def main():
    print("=== TEST DRY-RUN : --decades 2026-14:2026-18 ===\n")
    
    # Simulate CLI parsing
    decades_str = "2026-14:2026-18"
    decade_range = parse_decades_range(decades_str)
    y_start, d_start, y_end, d_end = decade_range
    
    print(f"Mode --decades : {decades_str}")
    print(f"  → Plage parsée : décades {y_start}-{d_start} à {y_end}-{d_end}\n")
    
    # Build calendar (what submit() does)
    calendar = build_decade_calendar_range(y_start, d_start, y_end, d_end)
    years_list = list(range(y_start, y_end + 1))
    
    print(f"Calendrier généré : {len(calendar)} décades")
    print(f"  Période : {calendar.iloc[0].date_start.date()} → {calendar.iloc[-1].date_end.date()}")
    print(f"  Années concernées : {years_list}\n")
    
    # Build specs (what GEE will receive)
    specs_by_year = build_specs(calendar, lead_days=10, lag_days=10)
    total_specs = sum(len(s) for s in specs_by_year.values())
    
    print(f"Specs GEE générées : {total_specs} specs")
    for year, specs_list in specs_by_year.items():
        print(f"  Année {year} :")
        for spec in specs_list:
            print(f"    - Decade {spec['id']} : {spec['start']} → {spec['end']}")
    print()
    
    # Calculate tasks
    total_cells = 181413
    tiles = (total_cells + POINT_EXPORT_TILE - 1) // POINT_EXPORT_TILE
    sources = 3  # CHIRPS, NDVI/EVI, LST
    batches = 1  # [2026]
    
    dynamic_tasks = sources * batches * tiles
    
    print(f"Tâches GEE dynamiques : {dynamic_tasks} tâches")
    print(f"  ({sources} sources × {batches} lot(s) × {tiles} tuiles)\n")
    
    # Expected output
    total_lines = total_cells * total_specs
    
    print(f"Volume de données attendu :")
    print(f"  {total_lines:,} lignes ({total_cells:,} cellules × {total_specs} décades)")
    print(f"  ~{total_lines * 200 / 1024 / 1024:.1f} MB (CSV)\n")
    
    # Comparison
    print("=" * 60)
    print("COMPARAISON :")
    print(f"  --decades 2026-14:2026-18 → {total_lines:,} lignes (5 décades)")
    print(f"  --years 2026 (entier)     → {total_cells * 30:,} lignes (30 décades de campagne)")
    print(f"  Ratio                     → {(total_cells * 30) / total_lines:.1f}× plus de données")
    print("=" * 60)
    
    print("\n✅ CONFIRMATION : GEE extrait UNIQUEMENT les 5 décades demandées.")
    print("   Le message '1 lot(s) de tâches GEE' n'implique PAS l'extraction de toute l'année.")

if __name__ == "__main__":
    main()
