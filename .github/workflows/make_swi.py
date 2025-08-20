# make_swi.py
import io, sys, datetime as dt, math, json
from pathlib import Path
import numpy as np
import requests
import xarray as xr
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm

# ----------------- Settings -----------------
# Great Lakes/NE North America bbox (lonW, lonE, latS, latN)
BBOX = (-92.0, -74.0, 40.5, 49.5)
OUT_PNG = Path("web/swi_overlay.png")
OUT_META = Path("web/swi_meta.json")  # carries bounds/timestamp for the viewer

# Contour levels and colors (low/moderate/high-ish)
LEVELS = [0, 10, 20, 30, 40, 50, 70]
COLORS = ["#00000000", "#4cc9f0", "#4895ef", "#4361ee", "#f59e0b", "#ef4444", "#b91c1c"]
# First color fully transparent so values <= 0 don’t render
assert len(COLORS) == len(LEVELS)

# ----------------- Helpers -----------------
def latest_cycle(now_utc):
    # Try most recent GFS cycles: 18Z, 12Z, 06Z, 00Z
    for h in [18, 12, 6, 0]:
        ctime = now_utc.replace(hour=h, minute=0, second=0, microsecond=0)
        if ctime <= now_utc:
            return ctime
    # fallback to previous day 18Z
    return (now_utc - dt.timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)

def fetch_gfs_subset(ts_cycle, bbox):
    yyyy = ts_cycle.strftime("%Y")
    ymd = ts_cycle.strftime("%Y%m%d")
    hh = ts_cycle.strftime("%H")
    leftlon, rightlon, lats, latn = bbox

    base = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    # Use f000 (analysis) for the cycle
    params = {
        "file": f"gfs.t{hh}z.pgrb2.0p25.f000",
        # Levels
        "lev_surface": "on",
        "lev_10_m_above_ground": "on",
        "lev_850_mb": "on",
        # Variables
        "var_tmp": "on",     # temperature (surface, 850 hPa)
        "var_ugrd": "on",    # u-wind 10 m
        "var_vgrd": "on",    # v-wind 10 m
        "var_cape": "on",    # CAPE surface
        # Geographic subset
        "leftlon": str(leftlon),
        "rightlon": str(rightlon),
        "toplat": str(latn),
        "bottomlat": str(lats),
        # Directory
        "dir": f"/gfs.{ymd}/{hh}/atmos",
        "format": "netcdf"
    }
    r = requests.get(base, params=params, timeout=120)
    r.raise_for_status()
    return xr.open_dataset(io.BytesIO(r.content))

def finite_diff_divergence(lon, lat, u10, v10):
    # Approximate horizontal divergence on lat/lon grid (in 1/s scale factors)
    # Convert degrees to meters
    R = 6371000.0
    lat_rad = np.deg2rad(lat)
    dlat = np.deg2rad(np.gradient(lat))[:, None]
    dlon = np.deg2rad(np.gradient(lon))[None, :]
    # Metric terms
    dy = dlat * R
    dx = dlon * R * np.cos(lat_rad)[:, None]

    du_dx = np.gradient(u10, axis=1) / dx
    dv_dy = np.gradient(v10, axis=0) / dy
    return du_dx + dv_dy

def scale_01(arr, qmin=0.05, qmax=0.95, clip=True):
    a = np.array(arr, dtype=float)
    lo = np.nanquantile(a, qmin)
    hi = np.nanquantile(a, qmax)
    out = (a - lo) / (hi - lo + 1e-9)
    if clip:
        out = np.clip(out, 0, 1)
    return out

def build_swi(ds):
    # Extract coordinates
    lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
    lon = ds["lon"].values if "lon" in ds else ds["longitude"].values

    # Extract fields (names may differ — harmonize)
    # Temperatures in K
    t_sfc = ds["tmp_surface"].squeeze().values  # K
    t850 = ds["tmp_850mb"].squeeze().values     # K

    # Convert to °C
    t_sfc_c = t_sfc - 273.15
    t850_c = t850 - 273.15
    dT = t_sfc_c - t850_c  # °C

    # Winds (m/s)
    u10 = ds["ugrd_10m"].squeeze().values
    v10 = ds["vgrd_10m"].squeeze().values
    div = finite_diff_divergence(lon, lat, u10, v10)  # 1/s
    conv = -div  # positive where convergent

    # CAPE (J/kg) as proxy for cloud depth (km) ~ sqrt(CAPE)/10
    cape = ds["cape_surface"].squeeze().values
    depth_km = np.sqrt(np.maximum(cape, 0.0)) / 10.0

    # Scale convergence into 0..1 (robust)
    conv_s = scale_01(conv)

    # SWI-like
    swi = dT * depth_km * conv_s
    return lon, lat, swi

def render_contours(lon, lat, swi, out_png):
    # Grid to image via contourf with transparent background
    fig = plt.figure(figsize=(8, 6), dpi=200)
    ax = plt.axes([0,0,1,1])  # full-bleed
    ax.set_axis_off()
    ax.set_xlim(lon.min(), lon.max())
    ax.set_ylim(lat.min(), lat.max())

    cmap = ListedColormap(COLORS)
    norm = BoundaryNorm(LEVELS, cmap.N, clip=False)

    # Use pcolormesh for speed and smoothness
    LON, LAT = np.meshgrid(lon, lat)
    m = ax.pcolormesh(LON, LAT, swi, cmap=cmap, norm=norm, shading="nearest")

    # Save with alpha channel
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, transparent=True)
    plt.close(fig)

def main():
    now = dt.datetime.utcnow()
    cyc = latest_cycle(now)
    ds = fetch_gfs_subset(cyc, BBOX)
    lon, lat, swi = build_swi(ds)
    render_contours(lon, lat, swi, OUT_PNG)

    # Write simple metadata for the viewer
    meta = {
        "generated_utc": now.isoformat() + "Z",
        "cycle_utc": cyc.isoformat() + "Z",
        "bounds": {"lon_w": BBOX[0], "lon_e": BBOX[1], "lat_s": BBOX[2], "lat_n": BBOX[3]},
        "levels": LEVELS
    }
    OUT_META.write_text(json.dumps(meta, indent=2))

if __name__ == "__main__":
    sys.exit(main())
