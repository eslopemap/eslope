import contextlib
from decimal import Decimal
import os
from pprint import pformat
import shutil
import sqlite3
import tempfile
from typing import List, Tuple, Union, Iterable, SupportsRound as Numeric
from unittest import TestCase

try:
    import mercantile as T
except ImportError:
    print('WARN: mercantile features not available')
    from unittest.mock import MagicMock as  T
LLBb = T.LngLatBbox


DB = Union[str, os.PathLike, sqlite3.Connection, sqlite3.Cursor]  # : 'TypeAlias'

@contextlib.contextmanager
def cursor(sqlite_or_path: DB, create=False):
    """Gracefully handle opening/closing db if necessary."""
    owndb = isinstance(sqlite_or_path, Union[str, bytes, os.PathLike])
    assert not owndb or os.path.exists(sqlite_or_path) or create, \
        f'Not found in {os.curdir}: {sqlite_or_path}'  # type: ignore
    db = sqlite3.connect(sqlite_or_path) if owndb else sqlite_or_path
    owncur = isinstance(db, sqlite3.Connection)
    dbc = db.cursor() if owncur else db
    try:
        yield dbc
    finally:
        if owndb and owncur:
            db.commit()
            db.close()
        if owncur and not owndb:
            dbc.close()


def mbt_info(mbt_or_cur: DB):
    if isinstance(mbt_or_cur, str):
        assert os.path.exists(mbt_or_cur), "Invalid path: " + mbt_or_cur

    with cursor(mbt_or_cur) as c:
        res = c.execute("SELECT 'zoom =', MIN(zoom_level), MAX(zoom_level), '; n =', COUNT(*) "
                        "FROM tiles ;").fetchall()
        if isinstance(mbt_or_cur, str):
            res.append(('*', round(os.path.getsize(mbt_or_cur) / res[0][4] / 1024), 'kb/tile'))
        try:
            import io, PIL.Image
            from src.jpg_quality_pil_magick import get_jpg_quality
            z, = c.execute("""SELECT MAX(zoom_level) FROM tiles""").fetchone()
            pim = PIL.Image.open(io.BytesIO(next(get_all_tiles(c, q=f'WHERE zoom_level={z}'))[-1]))
            if pim.format == 'JPEG':
                q = get_jpg_quality(pim)
                res.append(('q =', q))
        except:
            pass
        res += c.execute("SELECT ';', name, '=', value FROM metadata "
                         "WHERE name IN ('format', 'bounds', 'center', 'name');").fetchall()
        return ' '.join(' '.join(map(str, row)) for row in res)


def get_bounds(sqlite_or_path: DB, dbn:str='main') -> LLBb:
    with cursor(sqlite_or_path) as dbc:
        bstr, = dbc.execute(f"SELECT value FROM {dbn}.metadata WHERE name = 'bounds'").fetchone()
        return parse_bounds(bstr)

def parse_bounds(bstr) -> LLBb:
    return LLBb(*map(float, bstr.split(',')))

def get_bbounds(sqlite_or_path, dbn:str='main') -> LLBb:
    return LLBb(*get_bounds(sqlite_or_path, dbn))


def tms2bbox(z, *, x, y) -> LLBb:
    # Mercantile uses TXYZ but MBTiles use TMS -> flip
    y = (1 << z) - y - 1
    bb = T.xy_bounds(x, y, z)
    sw = T.lnglat(bb.left, bb.bottom)
    ne = T.lnglat(bb.right, bb.top)
    return LLBb(west=sw.lng, south=sw.lat, east=ne.lng, north=ne.lat)


def real_bounds(sqlite_or_path: DB, strict=False, dbn:str='main', zlevels:tuple=(), log=None) -> tuple[int, int, LLBb]:
    b_merge = b_intersection if strict else b_union
    bounds = None
    with cursor(sqlite_or_path) as dbc:
        rows = dbc.execute(f"""SELECT zoom_level, MIN(tile_column) x1w, MAX(tile_column) x2e,
                                                  MIN(tile_row) y1s, MAX(tile_row) y2n
                               FROM {dbn}.tiles GROUP BY zoom_level""").fetchall()
        zooms = [r[0] for r in rows]
        for z, x1w, x2e, y1s, y2n in rows:
            if not zlevels or z in zlevels:
                bbsw = tms2bbox(z, x=x1w, y=y1s)
                bbne = tms2bbox(z, x=x2e, y=y2n)
                zbounds = LLBb(bbsw.west, bbsw.south, bbne.east, bbne.north)
                if log:
                    log('real bounds ', z, [round(f, 2) for f in zbounds], x1w, y1s, x2e, y2n)
                bounds = LLBb(*b_merge(zbounds, bounds)) if bounds else zbounds
    return min(zooms), max(zooms), bounds


def set_real_bounds(sqlite_or_path: DB, dbn:str='main', log=lambda *a: None):
    with cursor(sqlite_or_path) as dbc:
        zmin, zmax, bb = real_bounds(dbc, dbn=dbn)
        c = compute_center(dbc, bb, dbn)
        update_mbt_meta(dbc, bounds=bb, center=c, zmin=zmin, zmax=zmax, log=log)


def compute_center(sqlite_or_path: DB, bounds:LLBb=None, dbn:str='main'):
    # center = None
    with cursor(sqlite_or_path) as dbc:
        bb = bounds or real_bounds(dbc)[2]
        (zc, _), = dbc.execute('SELECT min(zoom_level), max(zoom_level) FROM main.tiles')
        # first, try geographical bbox center
        lngc = float((bb.west + bb.east) / 2)
        latc = float((bb.south + bb.north) / 2)
        _, x, y = lnglat2tms(zc, lng=float(lngc), lat=float(latc))
        has_tile, = dbc.execute(
            f"SELECT COUNT(*) FROM {dbn}.tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (zc, x, y)).fetchone()
        # Fallback to first tile
        if not has_tile:
            for z, x, y in get_all_coords(dbc, q=f'WHERE zoom_level = {zc} LIMIT 1', arraysize=1):
                bb = tms2bbox(z, x=x, y=y)
                lngc = (bb.west + bb.east) / 2
                latc = (bb.south + bb.north) / 2
                print("Fallback `center` to first tile: ", z, x, y, lngc, latc)
        return T.LngLat(lngc, latc), zc


def compute_inner_bounds(sqlite_or_path: DB):
    '''Compute an heuristic of "strict" bounds for a square-ish map
      (for example full Bugianen is not square-ish!)
     by checking along the center lines'''

    if isinstance(sqlite_or_path, str):
        assert os.path.exists(sqlite_or_path)
    with cursor(sqlite_or_path) as dbc:
        # WITH... : find center x/y for each zoom (typically they double at each zoom)
        # 2 subqueries joining on fixed y then fixed x
        # then final UNION and SUM is just a way to pivot the data for clearer python code
        zwsen = dbc.execute(f"""
            WITH center AS MATERIALIZED (
                SELECT zoom_level AS z,
                    (MIN(tile_column) + MAX(tile_column)) / 2 AS c,
                    (MIN(tile_row) + MAX(tile_row)) / 2 AS r
                FROM tiles
                GROUP BY zoom_level)
            SELECT z, SUM(x1w), SUM(y1s), SUM(x2e), SUM(y2n)
            FROM (
                SELECT z, MIN(tile_column) x1w, 0 as y1s, MAX(tile_column) x2e, 0 as y2n
                FROM tiles JOIN center
                    ON zoom_level = z
                    AND tile_row = r
                GROUP BY zoom_level
                UNION ALL
                SELECT z, 0, MIN(tile_row) y1s, 0, MAX(tile_row) y2n
                FROM tiles JOIN center
                    ON zoom_level = z
                    AND tile_column = c
                GROUP BY z)
            GROUP BY z;
        """).fetchall()
        assert zwsen
        west_ = max(tms2bbox(z, x=w, y=1).west  for z, w, s, e, n in zwsen)
        south = max(tms2bbox(z, x=1, y=s).south for z, w, s, e, n in zwsen)
        east_ = min(tms2bbox(z, x=e, y=1).east  for z, w, s, e, n in zwsen)
        north = min(tms2bbox(z, x=1, y=n).north for z, w, s, e, n in zwsen)
        return LLBb(*(round(n, 5) for n in (west_, south, east_, north)))


def compute_strictest_bounds(sqlite_or_path: DB):
    '''Compute an heuristic of "strict" bounds for a square-ish map
      (for example full Bugianen is not square-ish!)
     by checking along the borders'''

    if isinstance(sqlite_or_path, str):
        assert os.path.exists(sqlite_or_path)
    with cursor(sqlite_or_path) as dbc:
        # WITH... : find center x/y for each zoom (typically they double at each zoom)
        # 2 subqueries joining on fixed y then fixed x
        # then final UNION and SUM is just a way to pivot the data for clearer python code
        zwsen = dbc.execute(f"""
            WITH border AS MATERIALIZED (
                SELECT zoom_level AS z,
                    MIN(tile_column) cw, MAX(tile_column) ce,
                    MIN(tile_row) rs, MAX(tile_row) rn
                FROM tiles
                GROUP BY zoom_level)
            SELECT z, SUM(x1w), SUM(y1s), SUM(x2e), SUM(y2n)
            FROM (
                SELECT z, MIN(tile_column) x1w, 0 as y1s, MAX(tile_column) x2e, 0 as y2n
                FROM tiles JOIN border
                    ON zoom_level = z
                    AND tile_row = rs
                GROUP BY zoom_level
                UNION ALL
                SELECT z, 0, MIN(tile_row) y1s, 0, MAX(tile_row) y2n
                FROM tiles JOIN border
                    ON zoom_level = z
                    AND tile_column = cw
                GROUP BY z)
            GROUP BY z
            UNION ALL
            SELECT z, SUM(x1w), SUM(y1s), SUM(x2e), SUM(y2n)
            FROM (
                SELECT z, MIN(tile_column) x1w, 0 as y1s, MAX(tile_column) x2e, 0 as y2n
                FROM tiles JOIN border
                    ON zoom_level = z
                    AND tile_row = rn
                GROUP BY zoom_level
                UNION ALL
                SELECT z, 0, MIN(tile_row) y1s, 0, MAX(tile_row) y2n
                FROM tiles JOIN border
                    ON zoom_level = z
                    AND tile_column = ce
                GROUP BY z)
            GROUP BY z;
        """).fetchall()
        assert zwsen
        west_ = max(tms2bbox(z, x=w, y=1).west  for z, w, s, e, n in zwsen)
        south = max(tms2bbox(z, x=1, y=s).south for z, w, s, e, n in zwsen)
        east_ = min(tms2bbox(z, x=e, y=1).east  for z, w, s, e, n in zwsen)
        north = min(tms2bbox(z, x=1, y=n).north for z, w, s, e, n in zwsen)
        return LLBb(*(round(n, 5) for n in (west_, south, east_, north)))



# FIXME this does not support bbox spanning (-)180°
def b_union(a, b):  # any kind of Bbox like W:S:E:N
    aleft, abottom, aright, atop = a
    bleft, bbottom, bright, btop = b
    return type(a)(min(aleft, bleft), min(abottom, bbottom), max(aright, bright), max(atop, btop))

def b_intersection(a, b):  # any kind of Bbox like W:S:E:N
    aleft, abottom, aright, atop = a
    bleft, bbottom, bright, btop = b
    return type(a)(max(aleft, bleft), max(abottom, bbottom), min(aright, bright), min(atop, btop))


def get_meta(mbt: DB, db='main'):
    with cursor(mbt) as dbc:
        return dict(dbc.execute(f'SELECT * FROM {db}.metadata').fetchall())


def update_with(source, dest, log=print):
    """Updates all tiles in `dest` with their "updated" version in `source`, if it exists."""
    assert source
    assert dest
    with cursor(dest) as dbc:
        dbc.execute(f'ATTACH "{source}" AS source')
        dbc.execute('''
            UPDATE main.tiles AS mt
            SET tile_data = st.tile_data
            FROM source.tiles AS st
            WHERE mt.zoom_level=st.zoom_level
              AND mt.tile_column=st.tile_column
              AND mt.tile_row=st.tile_row
        ''')
        log('Updated', dbc.rowcount)
        # dest_coords = set(get_all_coords(dest, q=q))
        # source_coords = set(get_all_coords(dest, q=q, dbn='source'))
        # coords = dest_coords.intersection(source_coords)
        # q = ''  # f'WHERE zoom_level in {str(z)}' if z else ''
        # for z in get_all_coords(dest, q=q):
        #     pass


def create_index(mbt: DB, log=print):
    with cursor(mbt) as dbc:
        # If no index, Ensure no duplicates in base file
        has_index, = dbc.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='index' AND tbl_name='tiles' AND sql LIKE 'CREATE UNIQUE%'""").fetchone()
        if not has_index:
            dbc.execute('''
                DELETE FROM tiles WHERE rowid NOT IN
                    (SELECT MAX(rowid) FROM tiles GROUP BY zoom_level, tile_column, tile_row)''')
            log(f'Deduplicated {dbc.rowcount} tiles.')
            dbc.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS zxy ON tiles (zoom_level, tile_column, tile_row);
            ''')


def mbt_merge(source, *more_sources:str, dest:str,
              name='', description='', attrib='', bb:LLBb=None, zmin:int=0, zmax:int=0, log=print):
    """ Does a "real" merge, relying on [Upsert](https://www.sqlite.org/lang_UPSERT.html),
         which was added to SQLite with version 3.24.0 (2018-06-04).
        It relies on an index for the conflict detection,
         but at least `gdal` and *Atlas Creator* have none, so:
          * we deduplicate, keep *last*
          * we create the index as needed
        (!) Assumes same image format
        (!) Later sources will take precedence on, overwrite and be "on top of" earlier ones
    """
    assert source
    assert dest.endswith('.mbtiles')
    new_mbt = not os.path.exists(dest)
    if new_mbt:
        name = name or dest[:-8]  # force a name
        if bb:
            cut_to_lnglat(source, bb=bb, dest=dest, zmin=zmin, zmax=zmax, log=log)
        else:
            log(f'cp {source} {dest}')
            shutil.copyfile(source, os.path.expanduser(dest))
            log('<<>>', source[:-8], ':', mbt_info(source))
    else:
        more_sources = (source, *more_sources)
    db = sqlite3.connect(dest)
    dbc = db.cursor()
    try:
        create_index(dbc)
        meta = dict(dbc.execute('SELECT * FROM metadata').fetchall())
        descm = f"Merge of the following files:\n* {meta['name']} : {meta.get('description', '')}\n"

        mbtcut = os.path.join(tempfile.gettempdir(), 'tmp.mbtiles')
        for source in more_sources:
            log('<<', source[:-8], ':', mbt_info(source))
            if bb:
                cut_to_lnglat(source, bb=bb, dest=mbtcut, zmin=zmin, zmax=zmax,
                              log=lambda *a, **k: None, overwrite=True)
                source = mbtcut
            # >> Merge tiles
            where = ''
            if zmin: where += 'zoom_level >= %s' % zmin
            if zmax: where += 'zoom_level <= %s' % zmax
            where = where or 'true'
            dbc.executescript(f'''
                ATTACH "{source}" AS source;
                INSERT INTO main.tiles
                    SELECT * FROM source.tiles WHERE {where}
                    ON CONFLICT (zoom_level, tile_column, tile_row)
                    DO UPDATE SET tile_data=excluded.tile_data;
            ''')
            # >> Merge description and bounds
            smeta = dict(dbc.execute('SELECT * FROM source.metadata').fetchall())
            meta.update(smeta)
            if 'name' in smeta:
                descm += f"* {smeta['name']} : {smeta.get('description','')}\n"

            # >> Detach to make room for next source
            dbc.execute(f'DETACH source;')
            if bb: os.unlink(mbtcut)
            log('>>', dest[:-8], ':', mbt_info(dbc))

        set_real_bounds(dbc, log=log)
        if new_mbt:  # otherwise keep existing meta
            print('Created:', name)
            update_mbt_meta(dbc, name=name, desc=description or descm, attrib=attrib)
    finally:
        dbc.close()
        db.commit()
        db.close()

# check that bounds merge work correctly

class TestMbt(TestCase):
    def test_bounds(self):
        b1 = get_bounds('Bugianen 2005 Cuneese.mbtiles')
        b2 = get_bounds('Bugianen 2005 Cervino.mbtiles')
        self.assertEqual(tuple(b1), tuple(map(Decimal, ('6.768','44.088','7.646','44.590'))))
        self.assertEqual(tuple(b2), tuple(map(Decimal, ('7.295','45.706','7.734','46.012'))))
        self.assertEqual(b_union(b1, b2),
                    LLBb(Decimal('6.768'), Decimal('44.088'), Decimal('7.734'), Decimal('46.012')))


def create_mbt(dbc: DB, dbn:str='main'):
    with cursor(dbc, create=True) as dbc:
        script = f'''

            CREATE TABLE IF NOT EXISTS {dbn}.tiles (
                zoom_level INTEGER NOT NULL,
                tile_column INTEGER NOT NULL,
                tile_row INTEGER NOT NULL,
                tile_data BLOB NOT NULL,
                UNIQUE (zoom_level, tile_column, tile_row)
            );

            CREATE TABLE IF NOT EXISTS {dbn}.metadata (
                name TEXT,
                value TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS {dbn}.zxy ON tiles (zoom_level, tile_column, tile_row);
            CREATE UNIQUE INDEX IF NOT EXISTS {dbn}.meta ON metadata (name);

        '''
        dbc.executescript(script)


def transfer_metadata(dbc: sqlite3.Cursor):
    """Assumption: cursor as a `main` (source) and `dest` (destination) database"""
    dbc.execute('INSERT INTO dest.metadata SELECT * FROM main.metadata')


def create_mbt_meta(sqlite_or_path: DB, name, desc, bounds:tuple, format, overwrite=True):
    update_mbt_meta(sqlite_or_path, name=name, desc=desc, bounds=bounds, format=format, overwrite=overwrite)


def update_mbt_meta(sqlite_or_path, name=None, desc=None, attrib=None,
                    bounds:Iterable[Numeric]=(), center:Iterable=(),
                    format=None, zmin=None, zmax=None,
                    _type='baselayer', db='main', overwrite=True, log=lambda *a: None):
    with cursor(sqlite_or_path) as dbc:
        dbc.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {db}.meta ON metadata (name)')
        meta = {}
        if bounds:
            meta['bounds'] = ','.join(map(lambda f: str(round(f, 5)), bounds))
        # boundstr = f'{bb.west:.5f},{bb.south:.5f},{bb.east:.5f},{bb.north:.5f}'
        if center:
            (lng, lat), z = center
            meta['center'] = f'{lng:.5f},{lat:.5f},{z}'
        args = {'name': name, 'description': desc, 'attribution': attrib, 'format': format,
                'minzoom': zmin, 'maxzoom': zmax, 'type': _type}
        for k, v in args.items():
            if k not in meta and bool(v):
                meta[k] = v
        on_conflict = 'DO UPDATE SET value=excluded.value' if overwrite else 'DO NOTHING'
        log('Meta update', pformat(meta))
        dbc.executemany(
            f'INSERT INTO {db}.metadata (name, value) VALUES (?, ?) ON CONFLICT (name) {on_conflict}',
            meta.items())
    # `format` is mandatory in 1.1+
    # `bounds` is optional but mandated by pmtiles
    # `center` is optional but mandated by pmtiles
    # `description` becomes optional later


def insert_tiles(sqlite_or_path, rows: 'List[Tuple[int, int, int, bytes]]', dbn='main'):
    """ rows: list of (z, x, y, im)"""
    # y = (1 << z) - y - 1
    if rows:
        with cursor(sqlite_or_path) as dbc:
            dbc.executemany(f'''
                INSERT INTO {dbn}.tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?,?,?,?)
                ON CONFLICT (zoom_level, tile_column, tile_row)
                DO UPDATE SET tile_data=excluded.tile_data ''', rows)


def update_tiles(dbc, rows: 'List[Tuple[bytes, int, int, int]]', dbname='main'):
    """ rows: list of (z, x, y, im)"""
    # y = (1 << z) - y - 1
    if rows:
        dbc.executemany(f'''
            UPDATE {dbname}.tiles SET tile_data = ?
            WHERE zoom_level=? AND tile_column=? AND tile_row=?
            ''', rows)
# def update

def remove_tiles(dbc, zxys: 'List[Tuple[int, int, int]]'):
    """ rows: list of (z, x, y, im)"""
    if zxys:
        dbc.executemany(f'''
            DELETE FROM tiles WHERE
             zoom_level=? AND tile_column=? AND tile_row=?''', zxys)


def sample_tile(mbt_or_cur: DB):
    """Random sample. Use num2tile or lnglat2tile if you have something in mind"""
    z, x, y, img = next(get_all_tiles(mbt_or_cur, arraysize=1))
    return img


def num2tile(sqlite_or_path: DB, z:int, x:int, y:int, flip_y:bool, what='tile_data', dbname='main'):
    # `flip_y`: MBTiles usesSW origing whereas OSM, Swisstop etc use NW origin
    # https://gis.stackexchange.com/questions/116288/mbtiles-and-slippymap-tilenames
    with cursor(sqlite_or_path) as dbc:
        if flip_y:
            y = (1 << z) - y - 1
        row = dbc.execute(f'SELECT {what} FROM {dbname}.tiles '
                    'WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                    [z, x, y]).fetchone()
        return (row[0] if len(row) == 1 else row) if row else None


def xyz2tile(dbc, t: 'T.Tile', flip_y=True, **kw):
    # Mercantile uses TXYZ but MBTiles use TMS -> flip
    return num2tile(dbc, t.z, t.x, t.y, flip_y=flip_y, **kw)


def lnglat2tile(dbc:'sqlite3.Cursor|str', z, *, lng:float, lat: float, **kw):
    """Wrapper for mercantile as it uses XYZ while MBTiles uses TMS
       It also does not support Decimal"""
    x, y, z = T.tile(lng, lat, z)
    return num2tile(dbc, z, x, y, flip_y=True, **kw)


def lnglat2tms(z, *, lng, lat):
    x, y, z = T.tile(lng, lat, z)
    y = (1 << z) - y - 1
    return z, x, y

# def tms2lnglat(z, *, lng, lat):
#     n = 2 ^ zoom
#     lon_deg = xtile / n * 360.0 - 180.0
#     lat_rad = arctan(sinh(π * (1 - 2 * ytile / n)))
#     lat_deg = lat_rad * 180.0 / π

# import math
# def lnglat2tms(lng, lat, z):
#   lat_rad = math.radians(lat)
#   n = 2.0 ** z
#   x = ((lng + 180.0) / 360.0 * n)
#   y = int(n * (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0)
#   y = (1 << z) - y - 1
#   return z, x, y

# def num2deg(xtile, ytile, zoom):
#   n = 2.0 ** zoom
#   lon_deg = xtile / n * 360.0 - 180.0
#   lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
#   lat_deg = math.degrees(lat_rad)
#   return (lat_deg, lon_deg)


def get_all_tiles(sqlite_or_path: DB, q='', arraysize=1000): # <- ~30MB RAM
    with cursor(sqlite_or_path) as dbc:
        dbc.execute('SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles ' + q)
        while rows:= dbc.fetchmany(arraysize):
            for row in rows:
                yield row


def get_all_coords(sqlite_or_path: DB, q='', arraysize=1000, dbn='main'): # <- ~30MB RAM
    with cursor(sqlite_or_path) as dbc:
        dbc.execute(f'SELECT zoom_level, tile_column, tile_row FROM {dbn}.tiles {q}')
        while rows:= dbc.fetchmany(arraysize):
            for row in rows:
                yield row


def tile_count(dbc: sqlite3.Cursor, dbn='main', q=''):
    return int(dbc.execute(f'SELECT COUNT(*) FROM {dbn}.tiles {q}').fetchone()[0])


def validate_src_dst(source, dest, overwrite=False, fun_inplace=False):
    """Common path handling:
       * if no overwrite, try to make a backup before raise.
       * handle source==dest by moving source
       * fun_inplace: True for functions which can operate with source==dest
    """
    dest = dest or source
    assert dest.endswith('.mbtiles') or dest.endswith('.mbt')
    if os.path.exists(dest):
        if overwrite and source != dest:
            os.unlink(dest)
            print('Overwriting ', dest)
        elif overwrite and fun_inplace:
            return source, dest  # leave as is
        else:
            bak = f'{dest[:-8]}.bak.mbtiles'
            assert not os.path.exists(bak), "not overwriting existing file " + bak
            print('Backing up dest as:', bak)
            os.rename(dest, bak)
            if source == dest:
                source = bak
    return source, dest


def apply_to_tiles(source: str, dest: str, fun, zooms: list[int]=[],
                   dbname='main', overwrite=False, log=print):
    assert dest and dest != source
    source, dest = validate_src_dst(source, dest, overwrite)
    if dest != source:
        log(f'cp {source} {dest}')
        dest = os.path.expanduser(dest)
        shutil.copyfile(source, dest)
    log('<<>>', source[:-8], ':', mbt_info(source))
    n = 0
    with cursor(dest) as dbc:
        if not zooms:
            (zmin, zmax), = dbc.execute('SELECT min(zoom_level), max(zoom_level) FROM main.tiles')
            zooms = list(range(zmin, zmax+1))
        for z in zooms:
            it = get_all_tiles(dbc, q=f'WHERE zoom_level = {z}')
            # OPTIM could do batches of ~100, insert with executemany
            for zoom_level, tile_column, tile_row, tile_data in it:
                n += 1
                new_data = fun(zoom_level, tile_column, tile_row, tile_data)
                q = f'''UPDATE {dbname}.tiles SET tile_data = ?
                        WHERE zoom_level=? AND tile_column=? AND tile_row=?  '''
                dbc.execute(q, (new_data, zoom_level, tile_column, tile_row))
    log(f"Changed {n} tiles")


def cut_zoom(source: str, zooms: list[int], dest: str='', overwrite=False):
    assert source.endswith('.mbtiles')
    assert not dest or dest.endswith('.mbtiles')
    if not dest:
        zname = ''.join(map(str, zooms)) if len(zooms) <= 2 else '-'.join(map(str, (zooms[0], zooms[-1])))
        dest = f'{source[:-8]}-z{zname}.mbtiles'
    assert dest != source
    source, dest = validate_src_dst(source, dest, overwrite)
    create_mbt(dest)
    with cursor(source) as dbc:
        dbc.execute(f'ATTACH "{dest}" AS dest;')
        nprev = 0
        for z in zooms:
            q = f'''
                INSERT INTO dest.tiles (zoom_level, tile_column, tile_row, tile_data)
                SELECT zoom_level, tile_column, tile_row, tile_data
                FROM main.tiles
                WHERE zoom_level = {z}
                '''
            dbc.execute(q)
            n, = dbc.execute('SELECT COUNT(*) FROM dest.tiles')
            print('z', z, ':', n[0] - nprev)
            nprev = n[0]
        transfer_metadata(dbc)
        set_real_bounds(dbc, dbn='dest')
    return dest


def cut_to_lnglat(source: str, bb: LLBb, dest: str='', zmin=None, zmax=None,
                  dbn='main', overwrite=False, log=print):
    """Cut MBTiles to given box, *including* tiles containing the border
    TODO use bbox.snap_to_xyz instead of duplicating functionality?"""
    source, dest = validate_src_dst(source, dest, overwrite, fun_inplace=False)
    log(mbt_info(source))
    log('cut_to_lnglat', source, '->', dest)
    create_mbt(dest)
    epsilon = 0.1**5 # around 1 pixel at z16
    with cursor(source) as dbc:
        dbc.execute(f'ATTACH "{dest}" AS dest;')
        nprev = 0

        if not zmin or not zmax:
            (zmindb, zmaxdb), = dbc.execute(f'SELECT min(zoom_level), max(zoom_level) FROM {dbn}.tiles')
            zmin = zmin or zmindb
            zmax = zmax or zmaxdb
            print(zmin, zmax, zmaxdb)
        for z in range(zmin, zmax+1):
            (x1west, y1south, x2east, y2north), =\
                dbc.execute(f'''SELECT
                    min(tile_column), min(tile_row),
                    max(tile_column), max(tile_row)
                FROM {dbn}.tiles WHERE zoom_level = ?''', (z,))
            if not x1west:
                log(f'z{z}: no tiles, skipping')
                continue
            _, xwest, ysouth = lnglat2tms(z, lng=bb.west+epsilon, lat=bb.south+epsilon)
            _, xeast, ynorth = lnglat2tms(z, lng=bb.east-epsilon, lat=bb.north-epsilon)
            xwest = max(xwest, x1west)
            ysouth = max(ysouth, y1south)
            xeast = min(xeast, x2east)
            ynorth = min(ynorth, y2north)
            if xwest > xeast or ysouth > ynorth:
                print(f"Warning: no overlap at zoom-level {z}, output may be unusable")
                continue
            q = f'''
                INSERT INTO dest.tiles (zoom_level, tile_column, tile_row, tile_data)
                SELECT zoom_level, tile_column, tile_row, tile_data
                FROM {dbn}.tiles
                WHERE zoom_level = {z}
                  AND tile_column >= {xwest} AND tile_column <= {xeast}
                  AND tile_row >= {ysouth} AND tile_row <= {ynorth}
                ON CONFLICT (zoom_level, tile_column, tile_row)
                DO UPDATE SET tile_data=excluded.tile_data;
                '''
            dbc.execute(q)
            n, = dbc.execute('SELECT COUNT(*) FROM dest.tiles')
            log(f'z {z}: +{n[0] - nprev} tiles: {xwest}<x<{xeast} {ysouth}<y<{ynorth}')
            nprev = n[0]
        transfer_metadata(dbc)
        set_real_bounds(dbc, dbn='dest', log=log)


def remove_lnglat(source: str, dest: str='', bb: LLBb=None, zmin=None, zmax=None,
                  overwrite=False, log=print):
    """Create `dest` as a copy of `source` with the tiles inside given bbox, border included removed
       The returned map is "complementary" to `cut_to_lnglat`.
       If only zmin/zmax are given, the whole zlevel(s) are removed.
    """
    assert bb or zmin or zmax
    source, dest = validate_src_dst(source, dest, overwrite, fun_inplace=True)
    if source != dest:
        log(f'cp {source} {dest}')
        dest = os.path.expanduser(dest)
        shutil.copyfile(source, dest)
    log('<<>>', source[:-8], ':', mbt_info(source))
    epsilon = 0.1**5 # around 1 pixel at z16
    with cursor(dest) as dbc:
        nprev, = dbc.execute('SELECT COUNT(*) FROM main.tiles').fetchone()
        if not zmin or not zmax:
            (zmindb, zmaxdb), = dbc.execute('SELECT min(zoom_level), max(zoom_level) FROM main.tiles')
            zmin = zmin or zmindb
            zmax = zmax or zmaxdb
            print(zmin, zmax, zmaxdb)
        for z in range(zmin, zmax+1):
            q = f'''
                DELETE FROM main.tiles
                WHERE zoom_level = {z}'''
            if bb:
                _, xwest, ysouth = lnglat2tms(z, lng=bb.west+epsilon, lat=bb.south+epsilon)
                _, xeast, ynorth = lnglat2tms(z, lng=bb.east-epsilon, lat=bb.north-epsilon)
                q += f'''
                  AND tile_column >= {xwest} AND tile_column <= {xeast}
                  AND tile_row >= {ysouth} AND tile_row <= {ynorth}
                '''
            dbc.execute(q)
            n, = dbc.execute('SELECT COUNT(*) FROM main.tiles').fetchone()
            print('z', z, ': removed', nprev - n)
            nprev = n
        set_real_bounds(dbc, log=log)
    with cursor(dest) as dbc:
        dbc.execute('VACUUM')


def remove_tile_xy(sqlite_or_path: DB, z: int, *, x, y):
    with cursor(sqlite_or_path) as dbc:
            q = f'''DELETE FROM main.tiles
                    WHERE zoom_level = {z} AND tile_column = {x} AND tile_row = {y} '''
            dbc.execute(q)


def remove_tile_ll(sqlite_or_path: DB, z: int, ll: T.LngLat):
    _, x, y= lnglat2tms(z, lng=ll.lng, lat=ll.lat)
    remove_tile_xy(sqlite_or_path, z, x=x, y=y)



def discard_bbox_borders(source: str, dest: str, zooms: list[int]=[], dbname='main', log=print):
    """(Unused, and unstable)
       Discard one row/column of tiles at ech of the 4 edges & borders of the map"""
    assert dest.endswith('.mbtiles')
    if dest != source:
        log(f'cp {source} {dest}')
        dest = os.path.expanduser(dest)
        shutil.copyfile(source, dest)
    log('<<>>', source[:-8], ':', mbt_info(source))
    with cursor(dest) as dbc:
        if not zooms:
            (zmin, zmax), = dbc.execute(f'SELECT min(zoom_level), max(zoom_level) FROM {dbname}.tiles')
            zooms = list(range(zmin, zmax+1))
        nprev, = dbc.execute(f'SELECT COUNT(*) FROM {dbname}.tiles')
        for z in zooms:
            (x1west, y1south, x2east, y2north), =\
                dbc.execute(f'''SELECT
                    min(tile_column), min(tile_row),
                    max(tile_column), max(tile_row)
                FROM {dbname}.tiles WHERE zoom_level = {z}''')
            q = f'''
                DELETE FROM {dbname}.tiles
                WHERE zoom_level = {z}
                  AND (tile_column == {x1west} OR tile_column == {x2east}
                    OR tile_row == {y1south} OR tile_row == {y2north})
                '''
            dbc.execute(q)
            n, = dbc.execute(f'SELECT COUNT(*) FROM {dbname}.tiles')
            print('z', z, ': removed', nprev[0] - n[0])
            nprev = n


class Tileset:
    @classmethod
    def from_db(cls, sqlite_or_path: DB, dbname='main'):
        self = cls()
        with cursor(sqlite_or_path) as dbc:
            dbc.execute(f'SELECT zoom_level, tile_column, tile_row FROM {dbname}.tiles ')
            while rows:= dbc.fetchmany(10000):
                for row in rows:
                    self.s.add(self.zxy_to_i(*row))
            return self

    def __init__(self) -> None:
        self.s = set()

    def __len__(self):
        return len(self.s)
    def __contains__(self, zxy):
        return self.zxy_to_i(*zxy) in self.s

    @classmethod
    def i_to_zxy(cls, i):
        mask17 = 0x1FFFF
        y = i & mask17
        rest = i >> 17
        x = rest & mask17
        rest >>= 17
        return rest, x, y

    @classmethod
    def zxy_to_i(cls, z, x, y):
        return (((z << 17) + x) << 17) + y

    def add_tile(self, z, x, y):
        self.s.add(self.zxy_to_i(z, x, y))
    def has_tile(self, z, x, y):
        return (z, x, y) in self.s
