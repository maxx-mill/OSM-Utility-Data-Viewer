import csv
import os
import json
import sys
from collections.abc import Iterator
import requests 


#define a hypothetical dictonary of field mappings

FIELD_MAP = {"mtr_num": "meter_id", "inst_dt": "install_date",
             "svc_type": "service_type", "lat": "latitude", "lon": "longitude"}

TRANSFORMS = {
    "to_float": float,
    "lower":    str.lower,
    "upper":    str.upper,
    "trim":     str.strip,
}

# Overpass endpoints -- tried in order, with retries (the public servers are flaky).
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
URL = ENDPOINTS[0]  # kept for back-compat

HEADERS = {"User-Agent": "osm-utility-data-viewer/0.1"}


def fetch_osm(query: str, retries: int = 2) -> list[dict]:
    """POST an Overpass query, trying each endpoint (with retries) until one succeeds."""
    for url in ENDPOINTS:
        for attempt in range(retries):
            try:
                response = requests.post(url, data={"data": query}, headers=HEADERS, timeout=25)
                response.raise_for_status()
                return response.json().get("elements", [])
            except requests.exceptions.RequestException as e:
                print(f"  {url} attempt {attempt + 1} failed: {e}")
    return []

def get_path(data: dict, path: str, default=""):
    current = data
    path = path.split(".")
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def load_rules(mapping_csv: str) -> list[dict]:
    rules = []
    with open(mapping_csv, mode='r', newline='', encoding='utf-8-sig') as file:
        # Initialize the DictReader
            csv_reader = csv.DictReader(file)

            for row in csv_reader:
                rules.append(row)

    return rules

def read_rows(input_csv: str) -> Iterator[dict[str, str]]:
    output_columns = list(FIELD_MAP.values())

    with open(input_csv, mode='r', encoding='utf-8') as file:
    # Initialize the DictReader
        csv_reader = csv.DictReader(file)

        for row in csv_reader:
            # print(row)
            yield row

def transform_row(row: dict[str,str], rules: list[dict[str,str]]) -> dict[str,str]:
    
    output = {}
    for rule in rules:
        out_name = rule["output_field"]
        src_name = rule["source_field"]
        raw = get_path(row, src_name, default="")
        op_name = rule["transform"]

        if op_name:
            func = TRANSFORMS[op_name]
            value = func(raw)
        else:
           value = raw

        output[out_name] = value
    
    return output

def write_rows(path: str, rows: list[dict[str,str]], field_names: list[str]) -> None:
    with open(path, mode='w', newline="", encoding='utf-8') as out_file:
        writer = csv.DictWriter(out_file, fieldnames=field_names)

        writer.writeheader()

        writer.writerows(rows)

def write_geojson(path, rows, lon_field="longitude", lat_field="latitude"):
    features = []
    for row in rows:
        props = dict(row)
        lon = props.pop(lon_field)
        lat = props.pop(lat_field)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })
    collection = {"type": "FeatureCollection", "features": features}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)


def main(in_path, out_path, mapping_csv):

    rules = load_rules(mapping_csv)

    raw_rows = read_rows(in_path)

    transformed = [transform_row(row, rules) for row in raw_rows]
    # print(renamed)

    field_names =  [rule["output_field"] for rule in rules]

    write_rows(out_path, transformed, field_names)

if __name__ == '__main__':
    in_csv = r"C:\Users\mills\workTools\sample_meters.csv"

    out_csv = r"C:\Users\mills\workTools\test.csv"

    map = r"C:\Users\mills\workTools\field_mapper\osm_towers_mapping.csv"
 
    main(in_csv, out_csv, map)