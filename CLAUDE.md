# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context

This workspace contains geospatial and tabular data for locust (*Locusta migratoria capito*) monitoring and preventive control in Madagascar. There is no source code yet — work here typically involves data analysis, GIS processing, and visualization using Python or R.

## Data Assets

All data lives under `data/`.

### Shapefiles (WGS 1984 / EPSG:4326)

**`aire_gregarigene/`** — 12 polygons representing locust gregarization zones (areas where locusts concentrate and form swarms).

Key fields:
- `AIRE_NOM` / `AIRE_CODE` — zone name and code
- `SECT_NOM` / `SECT_NO` — sector name and number
- `SUPER_AIRE` — parent super-zone ID
- `SUP_HA` — area in hectares

**`region_naturelle/`** — 90 polygons representing the natural regions of Madagascar.

Key fields:
- `rn_nom` — region name
- `rn_num` — region number
- `surfaces` — surface area

### Tabular Data

**`2001_2026_Acrido_vf.xls`** — Time-series acridological (locust) survey data covering 2001–2026.

### Reference Documents (PDF)

- `1979LecoqetalVoiesdedplacementLocusta.pdf` — Lecoq et al. 1979, locust displacement routes
- `LIVRE BLANC - EDGRND Décembre 2022.pdf` — EDGRND strategic white book
- `MANUEL DE LUTTE PRÉVENTIVE (VF).pdf` — preventive control field manual
- `Nicolas RANDRIANARIJAONA_Thèse_20260124.pdf` — doctoral thesis on Madagascar locust dynamics (2026)

## Recommended Libraries

For Python-based analysis:
- `geopandas` + `shapely` — shapefile reading and spatial operations
- `pandas` / `openpyxl` — reading the `.xls` survey data
- `matplotlib` / `contextily` — mapping and visualization
- `pyproj` — CRS transformations if reprojection is needed
réponds moi en français à chaque fois

## Agent skills

### Issue tracker

Issues live as local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
