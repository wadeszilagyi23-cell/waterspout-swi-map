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

# --- New resilient GFS fetch logic ---
MAX_CYCLES_BACK = 12  # check up to 3 days back
CYCLE_INTERVAL_HOURS = 6

def gfs_run_exists(url):
    """Check if a GFS run file exists before downloading."""
    try:
        r = requests.head(url, timeout=10)
        return r.status_code == 200
    except requests.RequestException:
        return False

def find_latest_gfs_url():
    """Search backwards for the most recent available GFS run."""
    now = datetime.datetime.utcnow()
    for i in range(MAX_CYCLES_BACK):
        run_time = now - datetime.timedelta(hours=i * CYCLE_INTERVAL_HOURS)
        cycle_str = run_time.strftime("%Y%m%d %HZ")
        url = (
            f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
            f"gfs.{run_time.strftime('%Y%m%d')}/{run_time.strftime('%H')}/atmos/"
            f"gfs.t{run_time.strftime('%H')}z.pgrb2.0p25.f000"
        )
        print(f"🔍 Checking GFS run {cycle_str}...")
        if gfs_run_exists(url):
            print(f"✅ Found available run: {cycle_str}")
            return url, cycle_str
    return None, None


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
        # Step 1 — Find the most recent available GFS run
gfs_url, gfs_cycle = find_latest_gfs_url()
if not gfs_url:
    print("⚠ No new GFS data found — using last successful SWI overlay. (Build skipped)")
    sys.exit(0)

print(f"🚀 Proceeding with SWI overlay build using GFS run {gfs_cycle}...")

# Download the data
response = requests.get(gfs_url)
response.raise_for_status()
with open("gfs_data.nc", "wb") as f:
    f.write(response.content)
print("💾 Saved gfs_data.nc")


        # Step 2 — Generate SWI overlay & metadata
        generate_swi_overlay("gfs_data.nc")
        print("🎉 SWI overlay creation complete.")
    except Exception as e:
        print(f"💥 Script failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

