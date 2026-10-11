"""Ingest OSM power towers for a bounding box into PostGIS (idempotent upsert).

Usage:   python ingest.py <south> <west> <north> <east>
Example: python ingest.py 51.25 12.20 51.45 12.60   # Leipzig
"""
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

import schemaforge as sf  # reuse the engine: fetch_osm, load_rules, transform_row

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

MAPPING = str(HERE / "osm_towers_mapping.csv")
TABLE = "towers"
COLS = ["asset_id", "asset_type", "asset_ref", "line_attachment", "material", "structure"]


def conn_params() -> dict:
    return dict(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def overpass_query(south, west, north, east) -> str:
    # Overpass bbox order is (south, west, north, east)
    return (
        "[out:json][timeout:60];\n"
        f'node["power"="tower"]({south},{west},{north},{east});\n'
        "out body;"
    )


def ensure_schema(cur) -> None:
    cur.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
              asset_id bigint, asset_type text, asset_ref text,
              line_attachment text, material text, structure text,
              geom geometry(Point, 4326)
            );"""
    )
    # unique index gives ON CONFLICT a target so re-runs/overlaps don't duplicate
    cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {TABLE}_asset_id_key ON {TABLE}(asset_id);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_geom_idx ON {TABLE} USING GIST(geom);")


def main(south, west, north, east) -> None:
    rules = sf.load_rules(MAPPING)
    elements = sf.fetch_osm(overpass_query(south, west, north, east))
    rows = [sf.transform_row(el, rules) for el in elements]
    print(f"fetched {len(elements)} elements -> {len(rows)} transformed rows")

    placeholders = ", ".join(["%s"] * len(COLS))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in COLS if c != "asset_id")
    upsert = (
        f"INSERT INTO {TABLE} ({', '.join(COLS)}, geom) "
        f"VALUES ({placeholders}, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) "
        f"ON CONFLICT (asset_id) DO UPDATE SET {updates}, geom = EXCLUDED.geom;"
    )
    values = [[r.get(c) for c in COLS] + [r["longitude"], r["latitude"]] for r in rows]

    conn = psycopg2.connect(**conn_params())
    try:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if values:
                cur.executemany(upsert, values)
            cur.execute(f"SELECT count(*) FROM {TABLE};")
            total = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    print(f"upserted {len(values)} towers; table now has {total} total")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit("usage: python ingest.py <south> <west> <north> <east>")
    s, w, n, e = map(float, sys.argv[1:5])
    main(s, w, n, e)
