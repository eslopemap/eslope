from decimal import Decimal
import os
import shutil
import sqlite3
from unittest import TestCase

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

def mbt_merge(source, *more_sources:str, dest:str, name='', log=print):
    """ Does a "real" merge, relying on [Upsert](https://www.sqlite.org/lang_UPSERT.html),
         which was added to SQLite with version 3.  24.0 (2018-06-04).
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
        dbc.executescript('''
            DELETE FROM tiles WHERE rowid NOT IN
                (SELECT MAX(rowid) FROM tiles GROUP BY zoom_level, tile_column, tile_row);
            CREATE UNIQUE INDEX IF NOT EXISTS xyz ON tiles (zoom_level, tile_column, tile_row);
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
        dbc.execute(f"UPDATE metadata SET value = '{desc}' WHERE name = 'description'")
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
