"""Ingest OSM power=line ways (LineStrings) for a bounding box into PostGIS.

Usage:   python ingest_lines.py <south> <west> <north> <east>
Example: python ingest_lines.py 51.00 6.80 51.06 6.90

Reuses the schemaforge engine for ATTRIBUTES (transform_row + a mapping); the only
line-specific part is building a LineString from the way's coordinate array.
"""
import json
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

import schemaforge as sf

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

MAPPING = str(HERE / "osm_lines_mapping.csv")
TABLE = "lines"
COLS = ["line_id", "name", "voltage", "operator", "line_ref", "cables", "circuits", "frequency"]


def conn_params() -> dict:
    return dict(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def overpass_query(south, west, north, east) -> str:
    return (
        "[out:json][timeout:60];\n"
        f'way["power"="line"]({south},{west},{north},{east});\n'
        "out geom;"  # returns each way with its full coordinate array
    )


def linestring_geojson(element) -> str:
    # OSM gives geometry as [{lat, lon}, ...]; GeoJSON wants [[lon, lat], ...]
    coords = [[p["lon"], p["lat"]] for p in element.get("geometry", [])]
    return json.dumps({"type": "LineString", "coordinates": coords})


def ensure_schema(cur) -> None:
    cur.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
              line_id bigint, name text, voltage text, operator text, line_ref text,
              cables text, circuits text, frequency text,
              geom geometry(LineString, 4326)
            );"""
    )
    cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {TABLE}_line_id_key ON {TABLE}(line_id);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_geom_idx ON {TABLE} USING GIST(geom);")


def main(south, west, north, east) -> None:
    rules = sf.load_rules(MAPPING)
    elements = sf.fetch_osm(overpass_query(south, west, north, east))

    rows = []
    for el in elements:
        if el.get("type") != "way" or len(el.get("geometry", [])) < 2:
            continue  # need at least two vertices for a line
        attrs = sf.transform_row(el, rules)        # same engine, different source
        rows.append([attrs.get(c) for c in COLS] + [linestring_geojson(el)])
    print(f"fetched {len(elements)} ways -> {len(rows)} usable lines")

    placeholders = ", ".join(["%s"] * len(COLS))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in COLS if c != "line_id")
    upsert = (
        f"INSERT INTO {TABLE} ({', '.join(COLS)}, geom) "
        f"VALUES ({placeholders}, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) "
        f"ON CONFLICT (line_id) DO UPDATE SET {updates}, geom = EXCLUDED.geom;"
    )

    conn = psycopg2.connect(**conn_params())
    try:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if rows:
                cur.executemany(upsert, rows)
            cur.execute(f"SELECT count(*) FROM {TABLE};")
            total = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    print(f"upserted {len(rows)} lines; table now has {total} total")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit("usage: python ingest_lines.py <south> <west> <north> <east>")
    s, w, n, e = map(float, sys.argv[1:5])
    main(s, w, n, e)
