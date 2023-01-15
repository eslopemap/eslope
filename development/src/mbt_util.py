import contextlib
from decimal import Decimal
import os
from pprint import pformat
import shutil
import sqlite3
from typing import List, Tuple, Union, Iterable, SupportsRound as Numeric
from unittest import TestCase

try:
    import mercantile as T
except ImportError:
    print('WARN: mercantile features not available')
    from unittest.mock import MagicMock as  T


DB = Union[str, bytes, os.PathLike, sqlite3.Connection, sqlite3.Cursor]  # : 'TypeAlias'

@contextlib.contextmanager
def cursor(sqlite_or_path: DB):
    """Gracefully handle opening/closing db if necessary."""
    owndb = isinstance(sqlite_or_path, Union[str, bytes, os.PathLike])
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
                        "FROM tiles ;").fetchall()\
            + c.execute("SELECT ';', name, '=', value FROM metadata "
                        "WHERE name IN ('format', 'bounds', 'center', 'name');").fetchall()
        return ' '.join(' '.join(map(str, row)) for row in res)


def get_bounds(sqlite_or_path: DB, dbn:str='main') -> T.LngLatBbox:
    with cursor(sqlite_or_path) as dbc:
        bstr, = dbc.execute(f"SELECT value FROM {dbn}.metadata WHERE name = 'bounds'").fetchone()
        return parse_bounds(bstr)

def parse_bounds(bstr) -> T.LngLatBbox:
    return T.LngLatBbox(*map(Decimal, bstr.split(',')))

def get_bbounds(sqlite_or_path, dbn:str='main') -> T.LngLatBbox:
    return T.LngLatBbox(*get_bounds(sqlite_or_path, dbn))


def tms2bbox(z, *, x, y) -> T.LngLatBbox:
    # Mercantile uses TXYZ but MBTiles use TMS -> flip
    y = (1 << z) - y - 1
    bb = T.xy_bounds(x, y, z)
    sw = T.lnglat(bb.left, bb.bottom)
    ne = T.lnglat(bb.right, bb.top)
    return T.LngLatBbox(west=sw.lng, south=sw.lat, east=ne.lng, north=ne.lat)


def real_bounds(sqlite_or_path: DB, db:str='main', zlevels:tuple=(), log=None) -> T.LngLatBbox:
    bounds = None
    with cursor(sqlite_or_path) as dbc:
        it = dbc.execute(f"""SELECT zoom_level, MIN(tile_column) x1w, MAX(tile_column) x2e,
                                                MIN(tile_row) y1s, MAX(tile_row) y2n
                             FROM {db}.tiles GROUP BY zoom_level""")
        for z, x1w, x2e, y1s, y2n in it:
            if not zlevels or z in zlevels:
                bbsw = tms2bbox(z, x=x1w, y=y1s)
                bbne = tms2bbox(z, x=x2e, y=y2n)
                zbounds = T.LngLatBbox(bbsw.west, bbsw.south, bbne.east, bbne.north)
                if log:
                    log('real bounds ', z, [round(f, 2) for f in zbounds], x1w, y1s, x2e, y2n)
                bounds = T.LngLatBbox(*b_union(zbounds, bounds)) if bounds else zbounds
    return bounds


def set_real_bounds(sqlite_or_path: DB, db:str='main'):
    with cursor(sqlite_or_path) as dbc:
        bb = real_bounds(dbc, db)
        print('real bounds:', bb)
        # boundstr = f'{bb.west:.5f},{bb.south:.5f},{bb.east:.5f},{bb.north:.5f}'
        update_mbt_meta(dbc, bounds=bb, center=compute_center(dbc, bb, db))
        # set_bounds(dbc, bounds)


def compute_center(sqlite_or_path: DB, bounds:T.LngLatBbox=None, db:str='main'):
    # center = None
    with cursor(sqlite_or_path) as dbc:
        bb = bounds or real_bounds(dbc)
        (zc, _), = dbc.execute('SELECT min(zoom_level), max(zoom_level) FROM main.tiles')
        # first, try geographical bbox center
        lngc = (bb.west + bb.east) / 2
        latc = (bb.south + bb.north) / 2
        _, x, y = lnglat2tms(zc, lng=float(lngc), lat=float(latc))
        has_tile, = dbc.execute(
            f"SELECT COUNT(*) FROM {db}.tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (zc, x, y)).fetchone()
        # Fallback to first tile
        if not has_tile:
            for z, x, y in get_all_coords(dbc, q=f'WHERE zoom_level = {zc} LIMIT 1', arraysize=1):
                bb = tms2bbox(z, x=x, y=y)
                lngc = (bb.west + bb.east) / 2
                latc = (bb.south + bb.north) / 2
                print("Fallback `center` to first tile: ", z, x, y, lngc, latc)
        return lngc, latc, zc


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


def mbt_merge(source, *more_sources:str, dest:str,
              name='', description='', attrib='', log=print):
    """ Does a "real" merge, relying on [Upsert](https://www.sqlite.org/lang_UPSERT.html),
         which was added to SQLite with version 3.24.0 (2018-06-04).
        It relies on an index for the conflict detection,
         but at least `gdal` and *Atlas Creator* have none, so:
          * we deduplicate, keep *last*
          * we create the index as needed
        (!) Assumes same image format
        (!) Later sources will take precedence on, overwrite and be "on top of" earlier ones
    """
    assert dest.endswith('.mbtiles')
    new_mbt = not os.path.exists(dest)
    if new_mbt:
        name = name or dest[:-8]  # force a name
        log(f'cp {source} {dest}')
        shutil.copyfile(source, os.path.expanduser(dest))
        log('<<>>', source[:-8], ':', mbt_info(source))
    else:
        more_sources = (source, *more_sources)
    db = sqlite3.connect(dest)
    dbc = db.cursor()
    try:
        # Ensure no duplicates in base file
        count, = dbc.execute("SELECT COUNT(*) FROM sqlite_master "
                             "WHERE type='index' AND tbl_name='tiles'").fetchone()
        if not count:
            log(f'Deduplicating {dest}....')
            dbc.executescript('''
                DELETE FROM tiles WHERE rowid NOT IN
                    (SELECT MAX(rowid) FROM tiles GROUP BY zoom_level, tile_column, tile_row);
                CREATE UNIQUE INDEX IF NOT EXISTS zxy ON tiles (zoom_level, tile_column, tile_row);
            ''')
        meta = dict(dbc.execute('SELECT * FROM metadata').fetchall())
        descm = f"Merge of the following files:\n* {meta['name']} : {meta['description']}\n"

        for source in more_sources:
            log('<<', source[:-8], ':', mbt_info(source))
            # >> Merge tiles
            dbc.executescript(f'''
                ATTACH "{source}" AS source;
                INSERT INTO main.tiles
                    SELECT * FROM source.tiles WHERE true
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
            log('>>', dest[:-8], ':', mbt_info(dbc))

        set_real_bounds(dbc)
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
                    T.LngLatBbox(Decimal('6.768'), Decimal('44.088'), Decimal('7.734'), Decimal('46.012')))


def create_mbt(dbc: DB, dbn:str='main'):
    with cursor(dbc) as dbc:
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
                    bounds:Iterable[Numeric]=(), center:Iterable[Numeric]=(),
                    format=None, minzoom=None, maxzoom=None,
                    _type='baselayer', db='main', overwrite=True, log=lambda *a: None):
    with cursor(sqlite_or_path) as dbc:
        dbc.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {db}.meta ON metadata (name)')
        meta = {}
        if bounds:
            meta['bounds'] = ','.join(map(lambda f: str(round(f, 5)), bounds))
        # boundstr = f'{bb.west:.5f},{bb.south:.5f},{bb.east:.5f},{bb.north:.5f}'
        if center:
            lng, lat, z = center
            meta['center'] = f'{lng:.5f},{lat:.5f},{z}'
        args = {'name': name, 'description': desc, 'attribution': attrib, 'format': format,
                'minzoom': minzoom, 'maxzoom': maxzoom, 'type': _type}
        for k, v in args.items():
            if k not in meta and bool(v):
                meta[k] = v
        on_conflict = 'DO UPDATE SET value=excluded.value' if overwrite else 'DO NOTHING'
        log(pformat(meta))
        dbc.executemany(
            f'INSERT INTO {db}.metadata (name, value) VALUES (?, ?) ON CONFLICT (name) {on_conflict}',
            meta.items())
    # `format` is mandatory in 1.1+
    # `bounds` is optional but mandated by pmtiles
    # `center` is optional but mandated by pmtiles
    # `description` becomes optional later


def insert_tiles(dbc, rows: 'List[Tuple[int, int, int, bytes]]', dbname='main'):
    """ rows: list of (z, x, y, im)"""
    # y = (1 << z) - y - 1
    if rows:
        dbc.executemany(f'''
            INSERT INTO {dbname}.tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?,?,?,?)
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
        return row[0] if row else None


def xyz2tile(dbc, t: 'T.Tile'):
    # Mercantile uses TXYZ but MBTiles use TMS -> flip
    return num2tile(dbc, t.z, t.x, t.y, flip_y=True)


def lnglat2tile(dbc:'sqlite3.Cursor|str', z, *, lng:float, lat: float):
    """Wrapper for mercantile as it uses XYZ while MBTiles uses TMS
       It also does not support Decimal"""
    x, y, z = T.tile(lng, lat, z)
    return num2tile(dbc, z, x, y, flip_y=True)


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


def get_all_coords(sqlite_or_path: DB, q='', arraysize=1000): # <- ~30MB RAM
    with cursor(sqlite_or_path) as dbc:
        dbc.execute('SELECT zoom_level, tile_column, tile_row FROM tiles ' + q)
        while rows:= dbc.fetchmany(arraysize):
            for row in rows:
                yield row


def tile_count(dbc: sqlite3.Cursor):
    return int(dbc.execute('SELECT COUNT(*) FROM tiles').fetchone()[0])


def apply_to_tiles(source: str, dest: str, fun, zooms: list[int]=[], dbname='main', log=print):
    assert dest != source
    assert dest.endswith('.mbtiles')
    assert not os.path.exists(dest), "not overwriting existing file"
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
    assert overwrite or not os.path.exists(dest), "not overwriting existing file"
    if os.path.exists(dest):
        os.unlink(dest)
        print('Overwriting ', dest)
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
        set_real_bounds(dbc, db='dest')
    return dest


def cut_to_lnglat(source: str, dest: str, bb: T.LngLatBbox, zmin=None, zmax=None, dbsrc='main', log=print):
    """Cut MBTiles to given box, *including* tiles containing the border
    TODO use bbox.snap_to_xyz instead of duplicating functionality?"""
    assert dest.endswith('.mbtiles')
    assert not os.path.exists(dest), "not overwriting existing file"
    create_mbt(dest)
    epsilon = 10 * T.LL_EPSILON
    with cursor(source) as dbc:
        dbc.execute(f'ATTACH "{dest}" AS dest;')
        nprev = 0

        if not zmin or not zmax:
            (zmindb, zmaxdb), = dbc.execute(f'SELECT min(zoom_level), max(zoom_level) FROM {dbsrc}.tiles')
            zmin = zmin or zmindb
            zmax = zmax or zmaxdb
            print(zmin, zmax, zmaxdb)
        for z in range(zmin, zmax+1):
            (x1west, y1south, x2east, y2north), =\
                dbc.execute(f'''SELECT
                    min(tile_column), min(tile_row),
                    max(tile_column), max(tile_row)
                FROM {dbsrc}.tiles WHERE zoom_level = ?''', (z,))
            _, xwest, ysouth = lnglat2tms(z, lng=bb.west+epsilon, lat=bb.south+epsilon)
            _, xeast, ynorth = lnglat2tms(z, lng=bb.east-epsilon, lat=bb.north-epsilon)
            xwest = max(xwest, x1west)
            ysouth = max(ysouth, y1south)
            xeast = min(xeast, x2east)
            ynorth = min(ynorth, y2north)
            print(z, xwest, '<>', xeast, ysouth, '<>', ynorth)
            if xwest > xeast or ysouth > ynorth:
                print(f"Warning: no overlap at zoom-level {z}, output may be unusable")
            q = f'''
                INSERT INTO dest.tiles (zoom_level, tile_column, tile_row, tile_data)
                SELECT zoom_level, tile_column, tile_row, tile_data
                FROM {dbsrc}.tiles
                WHERE zoom_level = {z}
                  AND tile_column >= {xwest} AND tile_column <= {xeast}
                  AND tile_row >= {ysouth} AND tile_row <= {ynorth}
                '''
            dbc.execute(q)
            n, = dbc.execute('SELECT COUNT(*) FROM dest.tiles')
            print('z', z, ': added', n[0] - nprev)
            nprev = n[0]
        transfer_metadata(dbc)
        set_real_bounds(dbc, db='dest')


def remove_lnglat(source: str, dest: str, bb: T.LngLatBbox, zmin=None, zmax=None, log=print):
    """Create `dest` as a copy of `source` with the tiles inside given bbox, border included removed
       The returned map is "complementary" to `cut_to_lnglat`
    """
    assert dest != source
    assert dest.endswith('.mbtiles')
    assert not os.path.exists(dest), "not overwriting existing file"
    log(f'cp {source} {dest}')
    dest = os.path.expanduser(dest)
    shutil.copyfile(source, dest)
    log('<<>>', source[:-8], ':', mbt_info(source))
    with cursor(dest) as dbc:
        nprev, = dbc.execute('SELECT COUNT(*) FROM dest.tiles')
        if not zmin or not zmax:
            (zmindb, zmaxdb), = dbc.execute('SELECT min(zoom_level), max(zoom_level) FROM main.tiles')
            zmin = zmin or zmindb
            zmax = zmax or zmaxdb
            print(zmin, zmax, zmaxdb)
        for z in range(zmin, zmax+1):
            _, xwest, ysouth = lnglat2tms(z, lng=bb.west, lat=bb.south)
            _, xeast, ynorth = lnglat2tms(z, lng=bb.east, lat=bb.north)
            q = f'''
                DELETE FROM main.tiles
                WHERE zoom_level = {z}
                  AND tile_column >= {xwest} AND tile_column <= {xeast}
                  AND tile_row >= {ysouth} AND tile_row <= {ynorth}
                '''
            dbc.execute(q)
            n, = dbc.execute('SELECT COUNT(*) FROM dest.tiles')
            print('z', z, ': removed', nprev - n[0])
            nprev = n[0]
        transfer_metadata(dbc)
        set_real_bounds(dbc)


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
