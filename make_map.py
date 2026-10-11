import folium

GEOJSON_PATH = r"C:\Users\mills\workTools\field_mapper\towers.geojson"
OUT_HTML = r"C:\Users\mills\workTools\field_mapper\towers_map.html"


def build_map(geojson_path: str, out_html: str) -> None:
    # Folium's Python API takes [lat, lon] -- the OPPOSITE of the
    # [lon, lat] order stored inside the GeoJSON file.
    m = folium.Map(
        location=[51.00, 6.85],
        zoom_start=13,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri",  # custom tile URLs require an attribution string
    )

    layer = folium.GeoJson(
        geojson_path,  # folium reads the file path directly
        name="power towers",
        marker=folium.CircleMarker(
            radius=5, color="#c0392b", fill=True, fill_color="#e74c3c", fill_opacity=0.8
        ),
        tooltip=folium.GeoJsonTooltip(
            fields=["asset_id", "asset_type", "asset_ref"],
            aliases=["Asset ID", "Type", "Ref"],
        ),
    )
    layer.add_to(m)

    m.fit_bounds(layer.get_bounds())  # auto-zoom to the data extent
    folium.LayerControl().add_to(m)   # toggle the layer on/off
    m.save(out_html)
    print("map written to:", out_html)


if __name__ == "__main__":
    build_map(GEOJSON_PATH, OUT_HTML)
