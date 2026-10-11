"""Flask app: serve PostGIS layers (towers, lines) as GeoJSON APIs and on a map.

Both layers use a cache pattern: the map reads them from PostGIS, and viewport-scoped
ingest endpoints pull them from OSM into PostGIS on demand.
"""
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from flask import Flask, Response, render_template, request

import ingest        # towers ingester (reused)
import ingest_lines  # lines ingester (reused)

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)

# `&&` is the bounding-box-overlap operator -- it uses the GIST spatial index.
BBOX_WHERE = "WHERE t.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"

BBOX_ERR = Response(
    '{"error": "bbox must be four numbers: west,south,east,north"}',
    status=400,
    mimetype="application/json",
)


def get_conn():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def fetch_geojson(table: str, bbox=None) -> dict:
    """Build a GeoJSON FeatureCollection from `table` (a trusted constant), optional bbox."""
    where = BBOX_WHERE if bbox else ""
    sql = f"""
        SELECT json_build_object(
          'type', 'FeatureCollection',
          'features', COALESCE(json_agg(ST_AsGeoJSON(t.*)::json), '[]'::json)
        )
        FROM {table} t
        {where};
    """
    params = tuple(bbox) if bbox else ()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = cur.fetchone()[0]
    finally:
        conn.close()
    return result if isinstance(result, dict) else json.loads(result)


def parse_bbox():
    """From ?bbox=w,s,e,n return [w,s,e,n] floats, None if absent, or 'bad' if malformed."""
    raw = request.args.get("bbox")
    if not raw:
        return None
    try:
        parts = [float(x) for x in raw.split(",")]
    except ValueError:
        parts = []
    return parts if len(parts) == 4 else "bad"


def _ingest(module, table, bbox):
    """Run an on-demand OSM ingest for the bbox, then report the in-view count."""
    w, s, e, n = bbox
    try:
        module.main(s, w, n, e)  # main(south, west, north, east)
    except Exception as exc:  # Overpass or DB hiccup
        return Response(
            json.dumps({"error": f"ingest failed: {exc}"}),
            status=502,
            mimetype="application/json",
        )
    gj = fetch_geojson(table, bbox)
    return Response(json.dumps({"ok": True, "count": len(gj["features"])}), mimetype="application/json")


@app.get("/api/towers")
def api_towers():
    bbox = parse_bbox()
    if bbox == "bad":
        return BBOX_ERR
    return Response(json.dumps(fetch_geojson("towers", bbox)), mimetype="application/json")


@app.get("/api/lines")
def api_lines():
    bbox = parse_bbox()
    if bbox == "bad":
        return BBOX_ERR
    return Response(json.dumps(fetch_geojson("lines", bbox)), mimetype="application/json")


@app.get("/api/towers/ingest")
def api_towers_ingest():
    bbox = parse_bbox()
    if bbox is None or bbox == "bad":
        return BBOX_ERR
    return _ingest(ingest, "towers", bbox)


@app.get("/api/lines/ingest")
def api_lines_ingest():
    bbox = parse_bbox()
    if bbox is None or bbox == "bad":
        return BBOX_ERR
    return _ingest(ingest_lines, "lines", bbox)


@app.get("/")
def index():
    return render_template("index.html")


def _ensure_tables():
    """Create both tables at startup so reads work before any ingest."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            ingest.ensure_schema(cur)
            ingest_lines.ensure_schema(cur)
        conn.commit()
    finally:
        conn.close()


_ensure_tables()


if __name__ == "__main__":
    app.run(debug=True)
