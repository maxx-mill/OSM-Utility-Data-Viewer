# OSM Utility Data Viewer

A config-driven **geospatial ETL + web-map app**: ingest utility infrastructure (power
towers and lines) from **OpenStreetMap**, normalize it to a target schema with a reusable
rules engine, cache it in **PostGIS**, and explore it on an interactive, viewport-driven map.

## Architecture

```
OSM Overpass API ──► fetch_osm ──► transform engine ──► GeoJSON ──► PostGIS ──► Flask ──► /api + map
                                   (rules + registry)    (write)    (indexed)
```

## What it does

- **Ingests** OSM features (e.g. `power=tower`) via the Overpass API.
- **Normalizes** messy source fields to a clean schema using a CSV **mapping file** — rename,
  type-cast, default, and transform via a small operation registry. Source fields support
  **dotted paths** (`tags.power`) so nested API data maps cleanly.
- **Loads** the result into a **PostGIS** table (`geometry(Point, 4326)` + GIST spatial index).
- **Serves** it with Flask: `GET /api/towers` returns GeoJSON (assembled in SQL by PostGIS),
  and `GET /` renders an interactive Folium/Leaflet map.

## Tech stack

Python · Flask · PostGIS (PostgreSQL) · psycopg2 · Folium/Leaflet · OSM Overpass API · GeoJSON

## Project structure

| File | Purpose |
|------|---------|
| `schemaforge.py` | the ETL engine: `fetch_osm`, `load_rules`, `transform_row`, `get_path`, `write_geojson` |
| `osm_towers_mapping.csv` | the OSM→schema mapping (the "config") |
| `load_to_postgis.py` | loads the GeoJSON into PostGIS |
| `app.py` | Flask GeoJSON API + map |
| `docker-compose.yml` | PostGIS via Docker (optional) |
| `towers.geojson` | sample output |

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Configure secrets — copy `.env.example` to `.env` and fill in your Postgres credentials.
3. Start PostGIS — either your local PostgreSQL (with the PostGIS extension) or Docker:
   ```
   docker compose up -d
   ```
4. Load the data and run the app:
   ```
   python load_to_postgis.py
   python app.py
   ```
   Then open http://127.0.0.1:5000/

## How the normalize engine works

The mapping CSV has one row per output field: `source_field, output_field, transform`. For each
input record, the engine resolves every rule's source (supporting nested `tags.x` paths), falls
back to a default when a field is missing, applies a named transform from a registry
(`to_float`, `upper`, ...), and stores it under the output name. A rename is just the identity
transform — so renaming and calculating are the same operation.

## Roadmap

- Move PostGIS fully to Docker Compose (compose file included)
- Bounding-box query param on the API (`/api/towers?bbox=...`) backed by the spatial index
- Additional OSM feature types and data sources
- Tests + CI
