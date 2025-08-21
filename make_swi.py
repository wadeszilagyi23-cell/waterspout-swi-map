# make_swi.py
import requests
import datetime
import sys
import time
import xarray as xr
import numpy as np
import json
import matplotlib.pyplot as plt

# Bounding box for your area of interest
BBOX = (-92.0, -74.0, 49.5, 40.5)  # leftlon, rightlon, toplat, bottomlat

def fetch_gfs_subset(cyc, bbox, retries=3, delay=60):
    """Download GFS subset for given cycle with retries."""
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    params = {
        "file": f"gfs.t{cyc['hour']:02d}z.pgrb2.0p25.f000",
        "lev_surface": "on",
        "lev_10_m_above_ground": "on",
        "lev_850_mb": "on",
        "var_tmp": "on",
        "var_ugrd": "on",
        "var_vgrd": "on",
        "var_cape": "on",
        "leftlon": bbox[0],
        "rightlon": bbox[1],
        "toplat": bbox[2],
        "bottomlat": bbox[3],
        "dir": f"/gfs.{cyc['date']}/{cyc['hour']:02d}/atmos",
        "format": "netcdf"
    }

    for attempt in range(1, retries + 1):
        r = requests.get(base_url, params=params)
        if r.status_code == 200:
            return r
        print(f"Attempt {attempt} failed with status {r.status_code}")
        if attempt < retries:
            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)

    raise requests.exceptions.HTTPError(
        f"All {retries} attempts failed for {cyc['date']} {cyc['hour']:02d}Z"
    )

def find_latest_available_run(bbox):
    """Find the most recent GFS run that is actually available."""
    now_utc = datetime.datetime.utcnow()
    cycle_hours = [0, 6, 12, 18]

    for hours_back in range(0, 24, 6):
        candidate_time = now_utc - datetime.timedelta(hours=hours_back)
        nearest_cycle_hour = max(h for h in cycle_hours if h <= candidate_time.hour)
        cyc = {
            "date": candidate_time.strftime("%Y%m%d"),
            "hour": nearest_cycle_hour
        }
        try:
            print(f"🔍 Trying GFS run {cyc['date']} {cyc['hour']:02d}Z...")
            r = fetch_gfs_subset(cyc, bbox)
            print(f"✅ Using GFS run {cyc['date']} {cyc['hour']:02d}Z")
            return r
        except Exception as e:
            print(f"❌ Failed for {cyc['date']} {cyc['hour']:02d}Z: {e}")

    raise RuntimeError("No recent GFS runs available — try again later.")

def generate_swi_overlay(nc_path):
    """Example SWI calculation + PNG/JSON output for Leaflet overlay."""
    ds = xr.open_dataset(nc_path)

    # Dummy SWI calculation — replace with real formula
    swi = ds['cape_surface'] / 1000.0  # scale CAPE values for demo

    plt.figure(figsize=(8, 6))
    plt.imshow(
        swi, origin='upper', cmap='RdYlBu_r',
        extent=[BBOX[0], BBOX[1], BBOX[3], BBOX[2]]
    )
    plt.colorbar(label='SWI')
    plt.title('Szilagyi Waterspout Index')
    plt.savefig('swi_overlay.png', bbox_inches='tight', transparent=True, dpi=150)
    plt.close()

    meta = {
        "bounds": [[BBOX[3], BBOX[0]], [BBOX[2], BBOX[1]]],
        "opacity": 0.6
    }
    with open('swi_meta.json', 'w') as f:
        json.dump(meta, f)

    print("🎯 Generated swi_overlay.png and swi_meta.json")

def main():
    try:
        # Step 1 — Download most recent available GFS data
        ds_response = find_latest_available_run(BBOX)
        with open("gfs_data.nc", "wb") as f:
            f.write(ds_response.content)
        print("💾 Saved gfs_data.nc")

        # Step 2 — Generate SWI overlay & metadata
        generate_swi_overlay("gfs_data.nc")
        print("🎉 SWI overlay creation complete.")
    except Exception as e:
        print(f"💥 Script failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

