"""Load towers.geojson into a PostGIS table using psycopg2 + raw SQL."""
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

GEOJSON = HERE / "towers.geojson"
TABLE = "towers"

# the non-geometry attribute columns (name -> postgres type)
COLUMNS = [
    ("asset_id", "bigint"),
    ("asset_type", "text"),
    ("asset_ref", "text"),
    ("line_attachment", "text"),
    ("material", "text"),
    ("structure", "text"),
]


def conn_params() -> dict:
    return dict(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def main() -> None:
    features = json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]
    col_names = [name for name, _ in COLUMNS]
    col_defs = ",\n          ".join(f"{name} {typ}" for name, typ in COLUMNS)

    # one placeholder per attribute, then lon/lat folded into a PostGIS point
    placeholders = ", ".join(["%s"] * len(col_names))
    insert_sql = (
        f"INSERT INTO {TABLE} ({', '.join(col_names)}, geom) "
        f"VALUES ({placeholders}, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
    )

    rows = []
    for f in features:
        props = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        rows.append([props.get(c) for c in col_names] + [lon, lat])

    conn = psycopg2.connect(**conn_params())
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
            cur.execute(f"CREATE TABLE {TABLE} (\n          {col_defs},\n          geom geometry(Point, 4326)\n);")
            cur.executemany(insert_sql, rows)
            cur.execute(f"CREATE INDEX ON {TABLE} USING GIST (geom);")  # spatial index
        conn.commit()
    finally:
        conn.close()

    print(f"loaded {len(rows)} features into table '{TABLE}'")


if __name__ == "__main__":
    main()
