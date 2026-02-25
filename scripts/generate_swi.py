import json
import random

# Mediterranean bounding box
lat_min = 30
lat_max = 46
lon_min = -6
lon_max = 37

grid_step = 0.5  # 🔥 upgraded resolution

features = []

lat = lat_min
while lat < lat_max:
    lon = lon_min
    while lon < lon_max:

        swi_value = round(random.uniform(0, 10), 2)

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lon, lat],
                    [lon + grid_step, lat],
                    [lon + grid_step, lat + grid_step],
                    [lon, lat + grid_step],
                    [lon, lat]
                ]]
            },
            "properties": {
                "swi": swi_value
            }
        }

        features.append(feature)

        lon += grid_step
    lat += grid_step

geojson = {
    "type": "FeatureCollection",
    "features": features
}

with open("data/med_swi_latest.geojson", "w") as f:
    json.dump(geojson, f)

print("SWI GeoJSON file generated.")
