from decimal import Decimal
import os
import shutil
import sqlite3
from typing import List, Tuple
from unittest import TestCase

try:
    import mercantile as T
except ImportError:
    print('WARN: mercantile features not available')
    from unittest.mock import MagicMock as  T


def get_bounds(db, dbn:str='main') -> 'tuple[Decimal, ...]': # -> w, s, e, n
    dbc = db if isinstance(db, sqlite3.Cursor) else sqlite3.connect(db).cursor()
    bstr, = dbc.execute(f"SELECT value FROM {dbn}.metadata WHERE name = 'bounds'").fetchone()
    return parse_bounds(bstr)

def parse_bounds(bstr):
    return tuple(map(Decimal, bstr.split(',')))

def set_bounds(w, s, e, n, dbc, db:str='main'):
    return dbc.execute(f"UPDATE {db}.metadata SET value = '{w},{s},{e},{n}' "
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
    if not os.path.exists(dest):
        log(f'cp {source} {dest}')
        shutil.copyfile(source, os.path.expanduser(dest))
        log('<<>>', source[:-8], ':', mbt_info(source))
    else:
        more_sources = (source, *more_sources)
    db = sqlite3.connect(dest)
    dbc = db.cursor()
    try:
        # Ensure no duplicates in base file
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
            set_bounds(*bounds, dbc)
            # >> Detach to make room for next source
            dbc.execute(f'DETACH source;')
            log('>>', dest[:-8], ':', mbt_info(dbc))

        print(name, desc)
        dbc.execute(f"UPDATE metadata SET value = '{name}' WHERE name = 'name'")
        dbc.execute(f"UPDATE metadata SET value = '{description or desc}' WHERE name = 'description'")
    finally:
        dbc.close()
        db.commit()
        db.close()

def mbt_info(mbt_or_cur):
    c = mbt_or_cur if isinstance(mbt_or_cur, sqlite3.Cursor)\
        else sqlite3.connect(mbt_or_cur).cursor()
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


def create_mbt(dbc: sqlite3.Cursor, dbn:str='main'):
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

# def copy_meta(dbcsrc, dbcdest):


def create_mbt_meta(dbc: sqlite3.Cursor, name, desc, bounds:tuple, format, overwrite=True):
    sbounds = ','.join(map(str, bounds))
    on_conflict = 'DO UPDATE SET value=excluded.value' if overwrite else 'DO NOTHING'
    dbc.executescript(f'''
        INSERT INTO metadata (name, value) VALUES
                    ("name", "{name}"),
                    ("description", "{desc}"),
                    ("bounds", "{sbounds}"),
                    ("format", "{format}")
                    ("type", "baselayer")
                    ON CONFLICT (name)
                    {on_conflict};
    ''')
    # `format` is mandatory in 1.1+
    # `bounds` is optional
    # `description` becomes optional in

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



def num2tile_impl(dbc:'sqlite3.Cursor', z, x, y, flip_y, what='tile_data', dbname='main'):
    if flip_y:
        y = (1 << z) - y - 1
    row = dbc.execute(f'SELECT {what} FROM {dbname}.tiles '
                'WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                [z, x, y]).fetchone()
    return row[0] if row else None


def num2tile(dbc, z, x, y, flip_y=False):
    # `flip_y`: MBTiles usesSW origing whereas OSM, Swisstop etc use NW origin
    # https://gis.stackexchange.com/questions/116288/mbtiles-and-slippymap-tilenames
    own = isinstance(dbc, str)
    if own:
        path = dbc
        assert os.path.exists(path)
        dbc = sqlite3.connect(path).cursor()
    try:
        im = num2tile_impl(dbc, z, x, y, flip_y)
        return im
    finally:
        if own:
            dbc.close()
            dbc.connection.close()

def xyz2tile(dbc, t: 'T.Tile'):
    # Mercantile uses TXYZ but MBTiles use TMS -> flip
    return num2tile(dbc, t.z, t.x, t.y, flip_y=True)

# def num2tile(dbc:'sqlite3.Cursor', z, x, y, flip_y=False):
    # own = isinstance(dbc, str)
    # if own:
    #     path = dbc
    #     assert os.path.exists(path)
    #     db = sqlite3.connect(path)
    #     dbc = db.cursor()
    # if flip_y:
    #     y = (1 << z) -y -1
    # row = dbc.execute('SELECT tile_data FROM tiles '
    #             'WHERE zoom_level=? AND tile_column=? AND tile_row=?',
    #             [z, x, y]).fetchone()
    # im = row[0] if row else None
    # if own:
    #     dbc.close()
    #     db.close()
    # return im


def lnglat2tile(dbc:'sqlite3.Cursor|str', z, *, lng, lat):
    x, y, z = T.tile(lng, lat, z)
    return num2tile(dbc, z, x, y, flip_y=True)

def get_all_tiles(db: sqlite3.Connection, q='', arraysize=1000): # <- ~30MB RAM
    dbc = db.cursor()
    try:
        dbc.execute('SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles ' + q)
        while rows:= dbc.fetchmany(arraysize):
            for row in rows:
                yield row
    finally:
        dbc.close()


def tile_count(dbc: sqlite3.Cursor):
    return int(dbc.execute('SELECT COUNT(*) FROM tiles').fetchone()[0])

class Tileset:
    @classmethod
    def from_db(cls, dbc: sqlite3.Cursor, dbname='main'):
        self = cls()
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


def get_tileset(db: sqlite3.Connection, q='', arraysize=1000): # <- ~30MB RAM
    dbc = db.cursor()
    try:
        dbc.execute('SELECT zoom_level, tile_column, tile_row FROM tiles ' + q)
        while rows:= dbc.fetchmany(arraysize):
            for row in rows:
                yield row
    finally:
        dbc.close()

def get_all_coords(db: sqlite3.Connection, q='', arraysize=1000): # <- ~30MB RAM
    dbc = db.cursor()
    try:
        dbc.execute('SELECT zoom_level, tile_column, tile_row FROM tiles ' + q)
        while rows:= dbc.fetchmany(arraysize):
            for row in rows:
                yield row
    finally:
        dbc.close()
