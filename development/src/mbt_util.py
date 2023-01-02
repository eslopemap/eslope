import contextlib
from decimal import Decimal
import os
import shutil
import sqlite3
from typing import List, Tuple, Union
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


# @contextlib.contextmanager
# def cursor(sqlite_or_path: DB):
#     """Gracefully handle opening/closing db if necessary."""
#     owncur = not isinstance(sqlite_or_path, sqlite3.Cursor)
#     owndb = owncur or not isinstance(sqlite_or_path, sqlite3.Connection)
#     db = sqlite3.connect(sqlite_or_path) if owncur or owndb else sqlite_or_path
#     dbc = db.cursor() if owncur else sqlite_or_path
#     try:
#         yield dbc
#     finally:
#         if owncur:
#             dbc.connection.commit()
#             dbc.close()
#             dbc.connection.close()


def get_bounds(sqlite_or_path, dbn:str='main') -> 'tuple[Decimal, ...]': # -> w, s, e, n
    with cursor(sqlite_or_path) as dbc:
        bstr, = dbc.execute(f"SELECT value FROM {dbn}.metadata WHERE name = 'bounds'").fetchone()
        return parse_bounds(bstr)

def parse_bounds(bstr):
    return tuple(map(Decimal, bstr.split(',')))

def set_bounds(sqlite_or_path: DB, w, s, e, n, db:str='main'):
    with cursor(sqlite_or_path) as dbc:
        return dbc.execute(f"UPDATE {db}.metadata SET value = '{w:.5f},{s:.5f},{e:.5f},{n:.5f}' "
                            "WHERE name = 'bounds'").fetchone()


def merge_bounds(w1, s1, e1, n1, w2, s2, e2, n2):
    return min(w1, w2), min(s1, s2), max(e1, e2), max(n1, n2)

def mbt_merge(source, *more_sources:str, dest:str, name='', description='', log=print):
    """ Does a "real" merge, relying on [Upsert](https://www.sqlite.org/lang_UPSERT.html),
         which was added to SQLite with version 3.24.0 (2018-06-04).
        It relies on an index for the conflict detection,
         but at least `gdal` and *Atlas Creator* have none, so:
          * we deduplicate, keep *last*
          * we create the index as needed
        (!) Assumes same image format
    """
    assert dest.endswith('.mbtiles')
    new_mbt = not os.path.exists(dest)
    if new_mbt:
        log(f'cp {source} {dest}')
        shutil.copyfile(source, os.path.expanduser(dest))
        log('<<>>', source[:-8], ':', mbt_info(source))
    else:
        more_sources = (source, *more_sources)
    db = sqlite3.connect(dest)
    dbc = db.cursor()
    try:
        # Ensure no duplicates in base file
        log(f'Deduplicating {dest}....')
        dbc.executescript('''
            DELETE FROM tiles WHERE rowid NOT IN
                (SELECT MAX(rowid) FROM tiles GROUP BY zoom_level, tile_column, tile_row);
            CREATE UNIQUE INDEX IF NOT EXISTS zxy ON tiles (zoom_level, tile_column, tile_row);
        ''')
        meta = dict(dbc.execute('SELECT * FROM metadata').fetchall())
        name = name or dest[:-8]
        desc = f"Merge of the following files:\n* {meta['name']} : {meta['description']}\n"
        bounds = parse_bounds(meta['bounds'])

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
            desc += f"* {smeta['name']} : {smeta['description']}\n"
            sbounds = parse_bounds(smeta['bounds'])
            bounds = merge_bounds(*bounds, *sbounds)
            set_bounds(dbc, *bounds)
            # >> Detach to make room for next source
            dbc.execute(f'DETACH source;')
            log('>>', dest[:-8], ':', mbt_info(dbc))

        if new_mbt:
            print('Created:', name, desc)
            dbc.execute(f"UPDATE metadata SET value = '{name}' WHERE name = 'name'")
            dbc.execute(f"UPDATE metadata SET value = '{description or desc}' WHERE name = 'description'")
    finally:
        dbc.close()
        db.commit()
        db.close()

def mbt_info(mbt_or_cur: DB):
    with cursor(mbt_or_cur) as c:
        res = c.execute("SELECT 'zoom =', MIN(zoom_level), MAX(zoom_level), '; n =', COUNT(*) "
                        "FROM tiles ;").fetchall()\
            + c.execute("SELECT ';', name, '=', value FROM metadata "
                        "WHERE name IN ('format', 'bounds');").fetchall()
        return ' '.join(' '.join(map(str, row)) for row in res)


# check that bounds merge work correctly

class TestMbt(TestCase):
    def test_bounds(self):
        b1 = get_bounds('Bugianen 2005 Cuneese.mbtiles')
        b2 = get_bounds('Bugianen 2005 Cervino.mbtiles')
        self.assertEqual(b1, tuple(map(Decimal, ('6.768','44.088','7.646','44.590'))))
        self.assertEqual(b2, tuple(map(Decimal, ('7.295','45.706','7.734','46.012'))))
        self.assertEqual(merge_bounds(*b1, *b2),
                    (Decimal('6.768'), Decimal('44.088'), Decimal('7.734'), Decimal('46.012')))


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


def create_mbt_meta(sqlite_or_path: DB, name, desc, bounds:tuple, format, overwrite=True):
    update_mbt_meta(sqlite_or_path, name=name, desc=desc, bounds=bounds, format=format, overwrite=overwrite)


def update_mbt_meta(sqlite_or_path, name=None, desc=None, bounds:tuple=None, format=None,
                    minzoom=None, maxzoom=None, overwrite=True):
    with cursor(sqlite_or_path) as dbc:
        dbc.execute('CREATE UNIQUE INDEX IF NOT EXISTS meta ON metadata (name)')
        meta = {"type": "baselayer"}
        if bounds:
            meta['bounds'] = ','.join(map(str, bounds))
        args = {'name': name, 'description': desc, 'format': format,
                'minzoom': minzoom, 'maxzoom': maxzoom}
        for k, v in args.items():
            if v is not None:
                meta[k] = v
        on_conflict = 'DO UPDATE SET value=excluded.value' if overwrite else 'DO NOTHING'
        dbc.executemany(
            f'INSERT INTO metadata (name, value) VALUES (?, ?) ON CONFLICT (name) {on_conflict}',
            meta.items())
    # `format` is mandatory in 1.1+
    # `bounds` is optional
    # `description` becomes optional later


def insert_tiles(dbc, rows: 'List[Tuple[int, int, int, bytes]]', dbname='main'):
    """ rows: list of (z, x, y, im)"""
    # y = (1 << z) - y - 1
    if rows:
        dbc.executemany(f'''
            INSERT INTO {dbname}.tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?,?,?,?)
            ON CONFLICT (zoom_level, tile_column, tile_row)
            DO UPDATE SET tile_data=excluded.tile_data ''', rows)

def update_tiles(dbc, rows: 'List[Tuple[int, int, int, bytes]]', dbname='main'):
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


def lnglat2tile(dbc:'sqlite3.Cursor|str', z, *, lng, lat):
    x, y, z = T.tile(lng, lat, z)
    return num2tile(dbc, z, x, y, flip_y=True)


def lnglat2tms(z, *, lng, lat):
    x, y, z = T.tile(lng, lat, z)
    y = (1 << z) - y - 1
    return z, x, y


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



def cut_to_lnglat(mbt_path_in: str, mbt_path_out: str, bb: T.LngLatBbox, zmin=None, zmax=None):
    """Cut MBTiles to given box
    TODO use bbox.snap_to_xyz instead of duplicating functionality"""
    create_mbt(mbt_path_out)
    with cursor(mbt_path_in) as dbc:
        #   cursor(mbt_path_out) as dbcout):
        dbc.execute(f'ATTACH "{mbt_path_out}" AS out;')
        nprev = 0

        if not zmin or not zmax:
            (zmindb, zmaxdb), = dbc.execute('SELECT min(zoom_level), max(zoom_level) FROM main.tiles')
            zmin = zmin or zmindb
            zmax = zmax or zmaxdb
            print(zmin, zmax, zmaxdb)
        for z in range(zmin, zmax+1):
            (c1west, r1south, c2east, r2north), =\
                dbc.execute(f'''SELECT
                    min(tile_column), min(tile_row),
                    max(tile_column), max(tile_row)
                FROM main.tiles WHERE zoom_level = {z}''')
            _, xwest, ysouth = lnglat2tms(z, lng=bb.west, lat=bb.south)
            _, xeast, ynorth = lnglat2tms(z, lng=bb.east, lat=bb.north)
            xwest = max(xwest, c1west)
            ysouth = max(ysouth, r1south)
            xeast = min(xeast, c2east)
            ynorth = min(ynorth, r2north)
            print(z, xwest, '<>', xeast, ysouth, '<>', ynorth)
            q = f'''
                INSERT INTO out.tiles (zoom_level, tile_column, tile_row, tile_data)
                SELECT zoom_level, tile_column, tile_row, tile_data
                FROM main.tiles
                WHERE zoom_level = {z}
                  AND tile_column >= {xwest} AND tile_column <= {xeast}
                  AND tile_row >= {ysouth} AND tile_row <= {ynorth}
                '''
            dbc.execute(q)
            n, = dbc.execute('SELECT COUNT(*) FROM out.tiles')
            print('z', z, ':', n[0] - nprev)
            nprev = n[0]


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
