#!/usr/bin/env python3
"""Standalone script (and importable module) for mapterhorn2eslo.

Usage from terminal (with live progress):
    cd development
    mamba activate -n maps
    python src/mapterhorn2eslo.py nolofotennz10 --locname 'Lofoten (Norway)' --reuse

Usage from Jupyter:
    from src.mapterhorn2eslo import mapterhorn2eslo, trr2tif
    mapterhorn2eslo('nolofotennz10', locname='Lofoten (Norway)', reuse=True)

Minimal pipeline:
```
wget https://download.mapterhorn.com/6-34-15.pmtiles -O data/dtm_local/<location>_trr.pmtiles
pmtiles-convert data/dtm_local/<location>_trr.{pmtiles,mbtiles}
python src/mapterhorn2eslo.py <location> --locname '<Location Name>' --reuse
```
A full tile like this can take 10 hours to process and use 50+GB of disk space.
All intermediate files are kept, stored in the `data/` directory.
"""

import argparse
import math
import os
import sys
from datetime import datetime
from subprocess import check_call, check_output, CalledProcessError

# ---------------------------------------------------------------------------
# check_run: live output in both terminal and Jupyter
# ---------------------------------------------------------------------------
try:
    from IPython.utils.process import system as _ipy_system  # type: ignore
    def check_run(cmd):
        r = _ipy_system(cmd)
        if r:
            raise CalledProcessError(r, cmd)
        return r
except ImportError:
    def check_run(cmd):
        return check_call(cmd, shell=True)

# ---------------------------------------------------------------------------
# Ensure we can import the local `src` package
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from src import gdal_slope_util as S, mbt_util as M

# ---------------------------------------------------------------------------
# Core functions (copied from notebook cell 10, kept identical)
# ---------------------------------------------------------------------------

def trr2tif(src, dest='', reuse=False):
    """Convert Terrarrium Terrain RGB MBTiles to GeoTIFF.
    This can takes ~2 minutes per GB and increase output file size by 30%.
    """
    assert dest or src.endswith('trr.mbtiles')
    dest = dest or src.replace('trr.mbtiles', 'dtm.tif')
    if reuse and os.path.exists(dest):
        print('Reuse', dest)
        return dest
    S.check_run(f"""
       gdal_calc.py \
        -A '{src}' --A_band=1 \
        -B '{src}' --B_band=2 \
        -C '{src}' --C_band=3 \
        --calc="(A*256.0 + B + C/256.0) - 32768" \
        --type=Float32 \
        --NoDataValue=-9999 \
        --co COMPRESS=ZSTD --co PREDICTOR=2 --co ZSTD_LEVEL=3 \
        --co TILED=YES --co blockXsize=1024 --co blockYsize=1024 \
        --co BIGTIFF=YES --co SPARSE_OK=TRUE --co NUM_THREADS=ALL_CPUS \
        --outfile='{dest}' \
        --overwrite
     """)


def mapterhorn2eslo(location, locname='', reuse=True):
    """Convert Mapterhorn Terrain extracts (Terrarrium) to eslope MBTile"""
    from osgeo import gdal

    f1trr = f'data/dtm_local/{location}_trr.mbtiles'
    f2dtm = f'data/dtm_local/{location}_dtm.tif'
    # f3utm no longer needed
    f4slo = f'data/slope_local/{location}_slopes.tif'
    f5zsl = f'data/slope_local/{location}_sz16.tif'
    f6mbt = f'data/mbtiles/eslo/eslo_{location}.mbtiles'
    if reuse and os.path.exists(f5zsl):
        print('Reuse', f5zsl)
    else:
        if reuse and os.path.exists(f4slo):
            print('Reuse', f4slo)
        else:
            if os.path.exists(f1trr):
                S.check_run(f"ls -lh '{f1trr}'")
            # 1. Convert Terrarrium Terrain RGB MBTiles to GeoTIFF
            trr2tif(f1trr, f2dtm, reuse=reuse)
            S.check_run(f"ls -lh '{f2dtm}'")

            # 2. Compute slope directly on Mercator DEM, with latitude correction.
            #
            # In EPSG:3857, pixel size in map units is constant (e.g. 2.389m at z16),
            # but actual ground distance per pixel is pixel_size * cos(lat).
            # gdaldem slope uses the GeoTransform pixel size as ground distance,
            # so it overestimates dx by 1/cos(lat), underestimating slopes.
            #
            # The -s flag scales horizontal distances: effective_dx = pixel_size / s
            # We need effective_dx = pixel_size * cos(lat), so s = 1/cos(lat_center).
            #
            # Error at latitude φ vs center φ₀: ε ≈ δ·tan(φ₀) where δ is the
            # half-span in radians. For 1° span at 70°N this is ~2.4%.

            ds = gdal.Open(f2dtm)
            gt = ds.GetGeoTransform()
            # center Y in EPSG:3857 meters then into latitude degrees
            cy_3857 = gt[3] + gt[5] * ds.RasterYSize / 2
            ds = None
            R = 6378137.0  # WGS84 semi-major axis (EPSG:3857 sphere radius)
            lat_center = math.degrees(2 * math.atan(math.exp(cy_3857 / R)) - math.pi / 2)
            scale = math.cos(math.radians(lat_center))
            print(f'Center latitude: {lat_center:.2f}°, -s scale factor: {scale:.4f}')
            S.check_run(S.printed(
                f"gdaldem slope {S.GDALDEM_CFG} '{f2dtm}' {S.DFLT_OPT} '{f4slo}' -s {scale}"))
            S.check_run(f"ls -lh '{f4slo}'")

            # 3. Merge slopes to MBTiles (no reprojection needed, already in EPSG:3857)
            S.warp_slopes(src=f4slo, dest=f5zsl, reuse=reuse)
    S.slope_mbt_5_zooms(src=f5zsl, dest=f6mbt, reuse=reuse)
    S.check_run(f"ls -lh '{f6mbt}'")
    name = 'eSlope {}'.format(locname or location[2:].capitalize())
    desc = 'Source data and license: https://mapterhorn.com/attribution/\n'\
        'Color ramp : https://github.com/eslopemap/eslope\n'\
        'Date generated : {}'.format(datetime.now().strftime('%Y-%m-%d'))
    M.update_mbt_meta(f6mbt, name=name, desc=desc, zmin=10, zmax=16, format='png')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert Mapterhorn Terrain extracts to eslope MBTiles.')
    parser.add_argument('locations', nargs='+',
                        help='Location ids, e.g. nolofotennz10 nolyngenz10')
    parser.add_argument('--locname', nargs='*', default=[],
                        help='Display names (one per location). '
                             'If fewer names than locations, remaining use default.')
    parser.add_argument('--reuse', action='store_true', default=True,
                        help='Reuse existing intermediate files (default: True)')
    parser.add_argument('--no-reuse', dest='reuse', action='store_false',
                        help='Force recompute all steps')
    args = parser.parse_args()

    # Ensure CWD is the development folder so relative data/ paths work
    if not os.path.isdir('data'):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print(f'Changing CWD to {script_dir}')
        os.chdir(script_dir)
    assert os.path.isdir('data'), \
        f"'data/' not found in {os.getcwd()}. Run from the development/ folder."
    assert os.path.isdir('data/dtm_local'), "'data/dtm_local/' not found."
    assert os.path.isdir('data/slope_local') or not True, \
        "'data/slope_local/' not found — creating it."
    os.makedirs('data/slope_local', exist_ok=True)

    os.environ['CPL_ZIP_ENCODING'] = 'UTF-8'

    for i, loc in enumerate(args.locations):
        locname = args.locname[i] if i < len(args.locname) else ''
        print(f'\n{"="*60}')
        print(f'  Processing: {loc}' + (f'  ({locname})' if locname else ''))
        print(f'{"="*60}\n')
        mapterhorn2eslo(loc, locname=locname, reuse=args.reuse)

    print('\nDone.')


if __name__ == '__main__':
    main()

#cd /home/eoubrayrie/mapproj/eslope/development
#mamba activate -n maps
#python run_mapterhorn2eslo.py nolofotennz10 nolyngenz10 --locname 'Lofoten (Norway)' 'Lyngen (Norway)' --reuse

