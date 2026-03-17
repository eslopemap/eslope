import os
from pathlib import Path
from posixpath import realpath
import re
from subprocess import check_call, check_output, CalledProcessError
from time import time
import rasterio

try:
    # like os.system but with live output
    from IPython.utils.process import system  #type:ignore
    def check_run(cmd):  # type:ignore
        r = system(cmd)
        if r: raise CalledProcessError(r, cmd)
        return r
except ImportError:
    def check_run(cmd):
        return check_call(cmd, shell=True)

from .mbt_util import mbt_merge, LLBb
from .bbox import BBox

resolutions = [
    156543.033928041, 78271.51696402048, 39135.758482010235, 19567.87924100512,
    9783.93962050256, 4891.96981025128, 2445.98490512564, 1222.99245256282,
    611.49622628141, 305.7481131407048, 152.8740565703525, 76.43702828517624,
    38.21851414258813, 19.10925707129406, 9.554628535647032, 4.777314267823516,
    2.388657133911758, 1.194328566955879, 0.5971642834779395, 0.2985821417389697,
    0.1492910708694849, 0.0746455354347424, 0.0373227677173712]


CMAPDIR_OLD = '~/code/eddy-geek/TIL/geo/data'
CMAPDIR = os.path.realpath(os.path.realpath(__file__) + '/../../data')

# ZSTD_LEVEL=3 bring an additional 15-20% at +60% processing cost, compared to L=1
ZSTD_OPT='-co COMPRESS=ZSTD -co ZSTD_LEVEL=3 '
TILE_OPT='-co TILED=YES -co blockXsize=1024 -co blockYsize=1024 '
XTIFF_OPT='-co BIGTIFF=YES -co SPARSE_OK=TRUE -co NUM_THREADS=ALL_CPUS '
GDALDEM_CFG='--config GDAL_CACHEMAX 2048 --config GDAL_ENABLE_READ_WRITE_MUTEX NO '  # workaround gdaldem + NUM_THREADS deadlock
WARP_PARAL_OPT='-multi -wo NUM_THREADS=ALL_CPUS ' # <- || compression, warp and compute
DFLT_OPT = ZSTD_OPT + TILE_OPT + XTIFF_OPT
DFLT_WARP_OPT = ZSTD_OPT + TILE_OPT + XTIFF_OPT + WARP_PARAL_OPT + '-overwrite '

def printed(foo):
    print(foo)
    return foo


def isfile(path):
    return os.path.isfile(os.path.expanduser(os.path.expandvars(path)))


def gdalwarp(src:str, dest:str, z=16, precision='', mode='nearest',
        extent:'BBox|str'='', default_opt=DFLT_WARP_OPT, extra_opt='', reuse=False):
    """ Gdalwarp wrapper
        :param z: to reproject/resample to a TMS zoom level `z`
        :param extent: eg `w s e n` in WGS84
        :param default_opt: to override default compression/tiling/tif etc
        :param extra_opt: any additional option"""
    if reuse and isfile(dest): print('Reuse', dest) ; return dest
    tr = '' if not z else \
         f'-tr {resolutions[z]} -{resolutions[z]}'
    if isinstance(extent, BBox):
        extent = f'-te_srs WGS84 -te {extent}'
    check_run(printed(f'''\
      gdalwarp {precision} \\
        {default_opt} \\
        -t_srs EPSG:3857 {tr} -r {mode} \\
        {extent} {extra_opt} \\
        {src} {dest}'''))


def warp_slopes(*,
        src: str, dest: str, z=16, precision='-ot Byte',
        extent:'BBox|str'='', default_opt=DFLT_WARP_OPT, extra_opt='', reuse=False):
    """Merge/reproject/resample to a TMS zoom level `z`
       Also rounds to Byte by default"""
    mode='nearest' if z == 16 else 'q3'
    extra_opt += ' -dstnodata 255 '  # to go with -ot Byte
    gdalwarp(src=src, dest=dest, z=z, precision=precision, mode=mode,
             extent=extent, default_opt=default_opt, extra_opt=extra_opt, reuse=reuse)


# def make_western_alps(*,
#         datafolder,
#         src=('fr/ignalps-lamb-slope.tif',
#             'it/piemont-utm32n-slope.tif',
#             'aoste/aoste-utm32n-slope.tif',
#             'alex/ignalex-lamb-slope.tif',
#             'ch/valais-lv95-slope.tif'),
#         dest='', z=16, precision='-ot Byte',
#         default_opt=DFLT_WARP_OPT,
#         extra_opt='', reuse=False):
#     mode='nearest' if z == 16 else 'q3'
#     dest = dest or 'AlpsW-slopes-z{z}.tif'
#     dest = os.path.realpath(dest)
#     extra_opt += ' -dstnodata 255 '
#     with Path(datafolder):  # <- FIXME
#         gdalwarp(w=w, s=s, e=e, n=n, src=src, dest=dest, z=z, precision=precision, mode=mode,
#                  default_opt=default_opt, extra_opt=extra_opt, reuse=reuse)


def cut_extent(*, src, dest='', z=16, precision='-ot Byte',
    extent='', default_opt=DFLT_WARP_OPT, extra_opt='', reuse=False):
    """
    :param precision: in decreasing order: -ot Float32 ; -co nbits=16 (p=0.03); -ot Byte (p=.5)
    """
    dest = dest or f'./slopes-z{z}.tif'
    gdalwarp(src=src, dest=dest, z=z, precision=precision,
             extent=extent, default_opt=default_opt, extra_opt=extra_opt, reuse=reuse)


def make_ovr(*, src: str, dest='', z,
             default_opt=DFLT_WARP_OPT, extra_opt='', r='q3', reuse=False):
    tr = resolutions[z]
    # replace the first occurrence of 'z#' or the last file extension with 'z#'
    dest = dest or re.sub(r'(z\d\d?\b)|(\.[^.]+)$', rf'z{z}\2', src, count=1)
    if reuse and isfile(dest): print('Reuse', dest); return dest
    check_run(printed(f'''\
      gdalwarp -r {r} -tr {tr} -{tr} \\
        {default_opt} {extra_opt} \\
        {src} {dest}'''))
    return dest


def slope_mbt(cname:str, *, z:int, options='', src='', dest='', reuse=False):
    """ Transforms DEM into color-coded slope mbtiles.
        :input cname: colorname eg `eslo13near`, to be found in `CMAPDIR/gdaldem-slope-{cname}.clr`
        :input zlevel: eg `16`
        :input options: gdaldem options eg `-alpha`
    """
    if src:
        # keep folder, insert cname and z in file name
        src_foldr, src_name = os.path.split(src)
        dest = f'{src_foldr}/{src_name.replace(".tif", "")}-{cname}-z{z}.mbtiles'
    else:
        src = src or f'./slopes-z{z}.tif'
        dest = dest or f'./{src}-{cname}-z{z}.mbtiles'
    if reuse and isfile(dest): print('Reuse', dest) ; return dest
    cmap = f'gdaldem-slope-{cname}.clr'
    # set nodata value to white so mbtiles blends correctly
    cmd = rf'''sed -e 's/nv \+0 \+0 \+0/nv  255 255 255/g' -e 's/nv \+#000000/nv #FFFFFF/g' '{CMAPDIR}/{cmap}' '''
    with open(f'/tmp/{cmap}', 'wb') as f:
        f.write(check_output(printed(cmd), shell=True))
    with open(f'/tmp/{cmap}') as f:
        for lineno, line in enumerate(f, 1):
            if '#' in line.split('%')[0]:  # ignore comments after %
                raise ValueError(f'/tmp/{cmap}:{lineno}: hex color not supported by gdaldem: {line.rstrip()}')
    check_run(printed(rf'''\
      gdaldem color-relief {src} /tmp/{cmap} {dest} \
          -nearest_color_entry -co TILE_FORMAT=png8 {options}'''))
    return dest

def slope_mbt_5_zooms(src: str, dest='', reuse=False):
    """Create an mbtile with lower zoom levels, from a z16 slope.
        Uses a z12 downsample (q3) as base for z13/z14, upsampled to target zoom.
    """
    zooms = {
        16: 'eslo13cnear',
        15: 'eslo13cnear',
        14: 'eslo4near',
        13: 'eslo4near',
    }
    if os.path.exists(dest):
        if reuse:
             print('Reuse', dest)
             return dest
        else:
            os.remove(dest)
    slope_z14 = make_ovr(src=src, z=14, r='q3', reuse=reuse)
    slope_z12 = make_ovr(src=slope_z14, z=12, r='q3', reuse=reuse)
    get_slope = {
        16: src,
        15: make_ovr(src=slope_z14, dest=slope_z14.replace('.tif', f'_up_z15.tif'),
                            z=15, r='bilinear', reuse=reuse),
        14: make_ovr(src=slope_z12, dest=slope_z12.replace('.tif', f'_up_z14.tif'),
                            z=14, r='bilinear', reuse=reuse),
        13: make_ovr(src=slope_z12, dest=slope_z12.replace('.tif', f'_up_z13.tif'),
                            z=13, r='bilinear', reuse=reuse),
    }
    files=[]
    for i, (z, cname) in enumerate(zooms.items()):
        chkpoint = time()
        to_merge = slope_mbt(cname, z=z, src=get_slope[z], reuse=reuse)
        files.append(os.path.expanduser(to_merge))
        print(f'Step {i+1}/{len(zooms)} completed in {round(time()-chkpoint,1)} seconds')

    mbt_merge(*files, dest=dest)
    add_white_z(dest, z=10)
    for f in slope_z14, slope_z12, get_slope[15], get_slope[14], get_slope[13]:
        os.unlink(f)
    return dest


def add_white_z(mbt: str, z=10, border_px=10):
    """Add a layer of transparent tiles at zoom level `z` covering the real bounds of `mbt`.

    Peripheral tiles get a semi-transparent blue border (alpha 30%) on their outward-facing
    edges.  Interior tiles are fully transparent white (255,255,255,0).
    """
    import io
    import sqlite3
    from PIL import Image, ImageDraw
    from .mbt_util import real_bounds, lnglat2tms, set_real_bounds

    _, _, bb = real_bounds(mbt)
    _, x_west, y_south = lnglat2tms(z, lng=float(bb.west), lat=float(bb.south))
    _, x_east, y_north = lnglat2tms(z, lng=float(bb.east), lat=float(bb.north))

    SZ = 256
    BLUE = (0, 0, 255, 77)  # 30% alpha ≈ 77/255

    def _make_tile(left, right, top, bottom):
        """Create a 256x256 RGBA PNG. Borders drawn on indicated sides."""
        img = Image.new('RGBA', (SZ, SZ), (255, 255, 255, 0))
        if left or right or top or bottom:
            draw = ImageDraw.Draw(img)
            b = border_px
            if top:    draw.rectangle([0, 0, SZ - 1, b - 1], fill=BLUE)
            if bottom: draw.rectangle([0, SZ - b, SZ - 1, SZ - 1], fill=BLUE)
            if left:   draw.rectangle([0, 0, b - 1, SZ - 1], fill=BLUE)
            if right:  draw.rectangle([SZ - b, 0, SZ - 1, SZ - 1], fill=BLUE)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    # Pre-build the transparent interior tile (reused for all interior tiles)
    interior_png = _make_tile(False, False, False, False)

    db = sqlite3.connect(mbt)
    dbc = db.cursor()
    n = 0
    for x in range(x_west, x_east + 1):
        for y in range(y_south, y_north + 1):
            is_left   = (x == x_west)
            is_right  = (x == x_east)
            is_bottom = (y == y_south)  # TMS: y_south is the southernmost (lowest) row
            is_top    = (y == y_north)
            if is_left or is_right or is_top or is_bottom:
                tile_png = _make_tile(is_left, is_right, is_top, is_bottom)
            else:
                tile_png = interior_png
            dbc.execute(
                'INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)',
                (z, x, y, tile_png))
            n += 1
    set_real_bounds(dbc)
    db.commit()
    db.close()
    print(f'add_white_z: inserted {n} tiles at z={z} ({x_west}..{x_east} x {y_south}..{y_north})')


def eslo_tiny(path: str, cname='eslo13bnear', res=0, where='/tmp', reuse=False):
    """For quick overviews. If file is big, use eg res=200. Detects `slope` in file name"""
    is_slope = 'slope' in os.path.basename(path)  # already a slope
    if res:
        p_tiny = where + '/tiny.tif'
        if not reuse or not os.path.exists(p_tiny):
            cmd = f'gdalwarp -overwrite -tr {res} -{res} {path} {p_tiny}'
            print(cmd); check_run(cmd)
        path = p_tiny
    p_slope = where + '/tiny_slope.tif'
    if is_slope:
        check_run(f'ln -sf {path} {p_slope}')
    else:
        cmd = f'gdaldem slope {GDALDEM_CFG} {path} {DFLT_OPT} {p_slope}'
        print(cmd); check_run(cmd)
    cmap = f'{CMAPDIR}/gdaldem-slope-{cname}.clr'
    p_relief = f'{where}/tiny_{cname}.png'
    check_run(printed(f'gdaldem color-relief {p_slope} {cmap} {p_relief} -nearest_color_entry'))
    return p_relief

def relief_tiny(*paths: str, res=0, where='/tmp'):
    """For quick overviews. If file is big, use eg res=200. Detects `slope` in file name"""
    path = ' '.join(map(str, paths))
    assert not 'slope' in os.path.basename(path)
    cmap = CMAPDIR_OLD + '/gdaldem-relief9.clr'
    if res:
        p_tiny = where + '/tiny.tif'
        check_run(printed(f'gdalwarp -overwrite {WARP_PARAL_OPT} -tr {res} -{res} {path} {p_tiny}'))
        path = p_tiny
    p_relief = f'{where}/tiny_relief.png'
    check_run(printed(f'gdaldem color-relief {path} {cmap} {p_relief}'))
    return p_relief

def get_bounds(dataset_path) -> LLBb:
    """Return WGS84 bounding box of a raster file as LLBb(w, s, e, n)."""
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(dataset_path) as ds:
        w, s, e, n = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    return LLBb(w, s, e, n)
