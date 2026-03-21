import io, sys, datetime as dt, json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import xarray as xr
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from scipy.interpolate import griddata

# ---------------- SETTINGS ----------------

BBOX = (-6.0, 37.0, 30.0, 46.5)

OUT_PNG = Path("web/swi_overlay.png")
OUT_META = Path("web/swi_meta.json")

REL_TABLE = "SWI Relational Data Points.xls"

LEVELS = [-10, -5, 0, 5, 10, 15, 20, 25, 30]
COLORS = [
    "#00000000",
    "#7dd3fc",
    "#38bdf8",
    "#0284c7",
    "#f59e0b",
    "#ef4444",
    "#b91c1c",
    "#7f1d1d"
]

# -----------------------------------------

def latest_cycle(now):
    for h in [18, 12, 6, 0]:
        c = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if c <= now:
            return c
    return (now - dt.timedelta(days=1)).replace(hour=18, minute=0)

def fetch_gfs(ts_cycle):

    ymd = ts_cycle.strftime("%Y%m%d")
    hh = ts_cycle.strftime("%H")

    url = (
        f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
        f"gfs.{ymd}/{hh}/atmos/gfs.t{hh}z.pgrb2.0p25.f006"
    )

    print("Downloading:", url)

    r = requests.get(url, timeout=300)
    r.raise_for_status()

    with open("gfs.grib2", "wb") as f:
        f.write(r.content)

    import cfgrib
    datasets = cfgrib.open_datasets("gfs.grib2")

    surface_ds = None
    pressure_ds = None

    for d in datasets:
        if "isobaricInhPa" in d.dims:
            pressure_ds = d
        else:
            surface_ds = d

    return surface_ds, pressure_ds

def load_relational_table():
    df = pd.read_excel(REL_TABLE, engine="xlrd")
    points = df[["delta T", "delta Z"]].values
    values = df["SWI"].values
    return points, values

def compute_swi(surface_ds, pressure_ds, points, values):

    # Coordinates
lat = surface_ds["latitude"].values
lon = surface_ds["longitude"].values

# --- SST (fallback to surface temp if missing)
if "sst" in surface_ds:
    sst = surface_ds["sst"].squeeze().values
else:
    sst = surface_ds["t"].squeeze().values  # fallback

# --- 850 mb temperature
t850 = pressure_ds["t"].sel(isobaricInhPa=850).squeeze().values

# --- CAPE
cape = surface_ds["cape"].squeeze().values

# Convert to Celsius
sst = sst - 273.15
t850 = t850 - 273.15

    # Apply bounding box
    lat_mask = (lat >= BBOX[2]) & (lat <= BBOX[3])
    lon_mask = (lon >= BBOX[0]) & (lon <= BBOX[1])

    lat = lat[lat_mask]
    lon = lon[lon_mask]

    sst = sst[np.ix_(lat_mask, lon_mask)]
    t850 = t850[np.ix_(lat_mask, lon_mask)]
    cape = cape[np.ix_(lat_mask, lon_mask)]

    # ΔT in °C
    dT = sst - t850

    # Cloud depth proxy (km)
    depth_km = np.sqrt(np.maximum(cape, 0)) / 10.0

    # Convert to feet
    dZ_m = depth_km * 1000.0
    dZ_ft = dZ_m * 3.28084

print("SST range:", np.nanmin(sst), np.nanmax(sst))
print("T850 range:", np.nanmin(t850), np.nanmax(t850))
print("CAPE range:", np.nanmin(cape), np.nanmax(cape))

    interp_points = np.column_stack((dT.flatten(), dZ_ft.flatten()))

    # Clip ΔT and ΔZ to the range of your relational table
dT_min, dT_max = points[:,0].min(), points[:,0].max()
dZ_min, dZ_max = points[:,1].min(), points[:,1].max()

dT_clipped = np.clip(dT, dT_min, dT_max)
dZ_clipped = np.clip(dZ_ft, dZ_min, dZ_max)

# Prepare points for interpolation
interp_points = np.column_stack((dT_clipped.flatten(), dZ_clipped.flatten()))

# Interpolate SWI using relational table
swi_flat = griddata(points, values, interp_points, method="linear")

swi = swi_flat.reshape(dT.shape)

# Replace any remaining NaN with minimum SWI (-10)
swi = np.nan_to_num(swi, nan=-10)

    return lon, lat, swi
# Ensure areas with no potential stay transparent
# SWI >= 0 → potential; SWI < 0 → no potential (transparent)
swi = np.where(swi >= 0, swi, -10)

def render(lon, lat, swi):

    fig = plt.figure(figsize=(8,6), dpi=200)
    ax = plt.axes([0,0,1,1])
    ax.set_axis_off()

    cmap = ListedColormap(COLORS)
    norm = BoundaryNorm(LEVELS, cmap.N)

    LON, LAT = np.meshgrid(lon, lat)
    ax.pcolormesh(LON, LAT, swi, cmap=cmap, norm=norm, shading="nearest")

    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PNG, transparent=True)
    plt.close(fig)

def main():

    now = dt.datetime.utcnow()
    cyc = latest_cycle(now)

    surface_ds, pressure_ds = fetch_gfs(cyc)
    points, values = load_relational_table()

    lon, lat, swi = compute_swi(surface_ds, pressure_ds, points, values)
    render(lon, lat, swi)

    meta = {
        "generated_utc": now.isoformat() + "Z",
        "cycle_utc": cyc.isoformat() + "Z",
        "bounds": {
            "lon_w": BBOX[0],
            "lon_e": BBOX[1],
            "lat_s": BBOX[2],
            "lat_n": BBOX[3]
        },
        "levels": LEVELS
    }

    OUT_META.write_text(json.dumps(meta, indent=2))

if __name__ == "__main__":
    sys.exit(main())
