import os
from pathlib import Path
import re
from subprocess import check_call, CalledProcessError
from time import time

try:
    # like os.system but with live output
    from IPython.utils.process import system
    def check_run(cmd):  # type:ignore
        r = system(cmd)
        if r: raise CalledProcessError(r, cmd)
        return r
except ImportError:
    def check_run(cmd):
        return check_call(cmd, shell=True)

from .mbt_util import mbt_merge

resolutions = [
    156543.033928041, 78271.51696402048, 39135.758482010235, 19567.87924100512,
    9783.93962050256, 4891.96981025128, 2445.98490512564, 1222.99245256282,
    611.49622628141, 305.7481131407048, 152.8740565703525, 76.43702828517624,
    38.21851414258813, 19.10925707129406, 9.554628535647032, 4.777314267823516,
    2.388657133911758, 1.194328566955879, 0.5971642834779395, 0.2985821417389697,
    0.1492910708694849, 0.0746455354347424, 0.0373227677173712]

CMAPDIR = '~/code/eddy-geek/TIL/geo/data'

ZSTD_OPT='-co COMPRESS=ZSTD -co PREDICTOR=2 -co ZSTD_LEVEL=1 '
TILE_OPT='-co TILED=YES -co blockXsize=1024 -co blockYsize=1024 '
XTIFF_OPT='-co BIGTIFF=YES -co SPARSE_OK=TRUE -co NUM_THREADS=ALL_CPUS '
WARP_PARAL_OPT='-multi -wo NUM_THREADS=ALL_CPUS ' # <- || compression, warp and compute
DFLT_OPT = ZSTD_OPT + TILE_OPT + XTIFF_OPT
DFLT_WARP_OPT = ZSTD_OPT + TILE_OPT + XTIFF_OPT + WARP_PARAL_OPT + '-overwrite '

def isfile(path):
    return os.path.isfile(os.path.expanduser(os.path.expandvars(path)))


def gdalwarp(w, s, e, n, *,
        src, dest, z=16, precision='-ot Byte', mode='nearest',
        default_opt=DFLT_WARP_OPT, extra_opt='', reuse=False):
    tr = resolutions[z]
    if reuse and isfile(dest): print('Reuse', dest) ; return 0
    cmd = f'''\
      gdalwarp {precision} \\
        {default_opt} {extra_opt} \\
        -t_srs EPSG:3857 -tr {tr} -{tr} -r {mode} \\
        -te_srs WGS84 -te {w} {s} {e} {n} \\
        {src} {dest}'''
    print(cmd)
    check_run(cmd)


def make_western_alps(w, s, e, n, *,
        datafolder,
        src=('fr/ignalps-lamb-slope.tif',
            'it/piemont-utm32n-slope.tif',
            'aoste/aoste-utm32n-slope.tif',
            'alex/ignalex-lamb-slope.tif',
            'ch/valais-lv95-slope.tif'),
        dest='', z=16, precision='-ot Byte',
        default_opt=DFLT_WARP_OPT,
        extra_opt='', reuse=False):
    mode='nearest' if z == 16 else 'q3'
    dest = dest or 'AlpsW-slopes-z{z}.tif'
    dest = os.path.realpath(dest)
    extra_opt += ' -dstnodata 255 '
    with Path(datafolder):  # <- FIXME
        gdalwarp(w=w, s=s, e=e, n=n, src=src, dest=dest, z=z, precision=precision, mode=mode,
                 default_opt=default_opt, extra_opt=extra_opt, reuse=reuse)


def cut_extent(w, s, e, n, *, src, dest='', z=16, precision='-ot Byte',
    default_opt=DFLT_WARP_OPT, extra_opt='', reuse=False):
    """`w s n e` : extent values
    :param precision: in decreasing order: -ot Float32 ; -co nbits=16 (p=0.03); -ot Byte (p=.5)
    """
    dest = dest or f'./slopes-z{z}.tif'
    gdalwarp(w=w, s=s, e=e, n=n, src=src, dest=dest, z=z, precision=precision,
             default_opt=default_opt, extra_opt=extra_opt, reuse=reuse)


def make_ovr(*, src, dest='', z,
             default_opt=DFLT_WARP_OPT, extra_opt='', reuse=False):
    tr = resolutions[z]
    dest = dest or re.sub(r'(z\d\d?\b)|(\.[^.]+)$', rf'z{z}\2', src, count=1)
    if reuse and isfile(dest): print('Reuse', dest) ; return 0
    cmd = f'''\
      gdalwarp -r q3 -tr {tr} -{tr} \\
        {default_opt} {extra_opt} \\
        {src} {dest}'''
    print(cmd)
    check_run(cmd)
    return dest


def slope_mbt(cname:str, *, z:int, options='', src='', reuse=False):
    """ Transforms DEM into color-coded slope mbtiles.
        :input cname: colorname eg `eslo13near`, to be found in `CMAPDIR/gdaldem-slope-{cname}.clr`
        :input zlevel: eg `16`
        :input options: gdaldem options eg `-alpha`
    """
    src = src or f'./slopes-z{z}.tif'
    dest = f'./{cname}-z{z}.mbtiles'
    if reuse and isfile(dest): print('Reuse', dest) ; return dest
    cmap = f'gdaldem-slope-{cname}.clr'
    cmd = f'''\
      sed 's/nv    0   0   0   0/nv  255 255 255 255/g' \\
          {CMAPDIR}/{cmap} >! /tmp/{cmap} && \\
      gdaldem color-relief {src} /tmp/{cmap} {dest} \\
          -nearest_color_entry -co TILE_FORMAT=png8 {options}'''
    print(cmd)
    check_run(cmd)
    return dest

def make_overviews(src, reuse=False):
    """Create an mbtile with lower zoom levels, from a z16 mbtiles
        Makes overviews with Q3 method as necessary, but prefer making your own.
    """
    zooms = {
        16: 'eslo13near',
        15: 'eslo13near',
        14: 'eslo4near',
        13: 'eslo4near',  # TBD oslo3near
        # 12: 'oslo2near', # TBD
    }
    src_foldr, src_name = os.path.split(src)
    destname = re.sub('slopes-?', '', src_name.replace('.tif',''))
    destname = re.sub('-?z16', '', destname)
    final_mbt = os.path.join(src_foldr, f'eslo{destname}.mbtiles')
    if os.path.exists(final_mbt):
        if reuse:
             print('Reuse', final_mbt)
             return final_mbt
        else:
            os.remove(final_mbt)
    files=[]
    for i, (z, cname) in enumerate(zooms.items()):
        chkpoint = time()
        zoomed_slope = src if z==16 else make_ovr(src=src, z=z, reuse=reuse)
        to_merge = slope_mbt(cname, z=z, src=zoomed_slope, reuse=reuse)
        files.append(os.path.expanduser(to_merge))  # f'{cname}-z{z}.mbtiles')
        print(f'Step {i+1}/{len(zooms)} completed in {round(time()-chkpoint,1)} seconds')

    mbt_merge(*files, dest=final_mbt)
