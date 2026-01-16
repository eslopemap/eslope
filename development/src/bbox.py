import sys
assert sys.version_info >= (3,7)
from dataclasses import dataclass, astuple
from typing import Tuple, cast
from unittest import TestCase

import mercantile as T


llclapier   = T.LngLat(7.42 , 44.115)
llmalinvern = T.LngLat(7.189, 44.199)

llorcieres  = T.LngLat(6.327, 44.683)
llstgeoire  = T.LngLat(5.59,  45.45) # SwissTopo z11 SW corner, north of Grenoble
lltignes    = T.LngLat(6.9,   45.47) # same, on z11 S line
llaixbains  = T.LngLat(5.9,   45.7) # SwissTopo z10,12 SW corner

llaostesud  = T.LngLat(7.328, 45.71)

# Mont Blanc Area
llmidi      = T.LngLat(6.887, 45.88)
llemosson   = T.LngLat(6.938, 46.067)
llferret    = T.LngLat(7.068, 45.898)
llmontets   = T.LngLat(6.93,  46)
llmiage     = T.LngLat(6.81,  45.825)
llmagland   = T.LngLat(6.624, 46.02)
llflainel   = T.LngLat(6.67,  46)
llflaine    = T.LngLat(6.69,  46)
# ll   = T.LngLat()
# ll   = T.LngLat()

# Zmutt near Zermatt / Breuil Aoste
llzmutt     = T.LngLat(7.7171, 46.0065)
llbreuil    = T.LngLat(7.6393, 45.9406)

# Gondo and Trasquera (Simplon pass - CH an IT)
llgondo     = T.LngLat(8.140, 46.196)
lltrasquera = T.LngLat(8.225, 46.21)

# Resia pass
llresia = T.LngLat(10.50, 46.83)

@dataclass
class BBox:
    """The field order maps mercantile and gdal's W:S:E:N, `-te_srs WGS84 -te 7.38 44 7.44 44.15`"""
    w: float
    s: float
    e: float
    n: float

    @classmethod
    def from_llbb(cls, bb: T.LngLatBbox):
        return cls(bb.west, bb.south, bb.east, bb.north)
    def to_llbb(self):
        return T.LngLatBbox(self.w, self.s, self.e, self.n)


    def __post_init__(self):
        if self.e > 40:
            print('WARN: East>40', file=sys.stderr)

    def astuple(self):
        return cast(Tuple[float, float, float, float], astuple(self))
    def __str__(self, p=6) -> str:
        return f'{self.w:.{p}f} {self.s:.{p}f} {self.e:.{p}f} {self.n:.{p}f}'
    def __iter__(self):
        return iter((self.w, self.s, self.e, self.n))

    def enlarge(self, eps=0.001):
        return BBox(self.w - eps, self.s - eps, self.e + eps, self.n + eps)
    def round(self, digits=3):
        return BBox(round(self.w, digits),round(self.s, digits), round(self.e, digits), round(self.n, digits))

    def intersect(self: 'BBox', c: 'BBox'):
        b = self
        # No rectangle is on the right, nor above, each other
        # https://gamedev.stackexchange.com/a/913/158443
        return not (b.w >= c.e or c.w >= b.e or b.s >= c.n or c.s >= b.n)
    def intersection(self: 'BBox', rect2: 'BBox'):
        rect1 = self
        if not rect1.intersect(rect2):
            raise ArithmeticError()
        return BBox(max(rect1.w, rect2.w), max(rect1.s, rect2.s),\
                    min(rect1.e, rect2.e), min(rect1.n, rect2.n))

    def snap_to_xyz(self: 'BBox', z:int, mode='~'):
        """A bit like `mercantile.bounding_tile` but with custom z"""
        assert mode in ('~', '+', '-')  # closest / enlarge / crop
        import mercantile as T
        w, s, e, n = self.w, self.s,  self.e, self.n
        tnw_big = T.tile(w, n, z)  # NW origin (== OSM web... ; != TMS MBTiles)
        tse_sml = T.tile(e, s, z)
        nw_sml = T.ul(T.Tile(tnw_big.x+1, tnw_big.y+1, z)) # >T<ile
        nw_big = T.ul(tnw_big)
        se_sml = T.ul(tse_sml)
        se_big = T.ul(T.Tile(tse_sml.x+1, tse_sml.y+1, z)) # >T<ile
        if mode == '+':  # biggest (enlarge)
            return BBox(w=nw_big.lng, s=se_big.lat, e=se_big.lng, n=nw_big.lat)
        elif mode == '-': # smallest (crop)
            return BBox(w=nw_sml.lng, s=se_sml.lat, e=se_sml.lng, n=nw_sml.lat)
        elif mode == '~':  # closest
            return BBox(
                w=closest_to(w, nw_sml.lng, nw_big.lng),
                s=closest_to(s, se_sml.lat, se_big.lat),
                e=closest_to(e, se_sml.lng, se_big.lng),
                n=closest_to(n, nw_sml.lat, nw_big.lat))
        raise NotImplementedError


def enlarge(bb: T.LngLatBbox, eps=0.001):
    return BBox.from_llbb(bb).enlarge(eps=eps).to_llbb()

def snap_to_xyz(bb: T.LngLatBbox, z:int, mode='~'):
    return BBox.from_llbb(bb).snap_to_xyz(z=z, mode=mode).to_llbb()

def closest_to(n, n1, n2):
    return n1 if abs(n1-n) < abs(n2-n) else n2


bbalps_z6 = BBox(0.000000, 40.979897, 16.874996, 48.922497)
# Beziers - Vienna
bbalps_z7 = BBox(2.812499, 43.068887, 16.874996, 48.922497)
# Camargues - Mariazell
bbalps_z8 = BBox(4.218749, 43.068887, 15.468747, 47.989920)
#  - Kapfenberg
bbalps_z9 = BBox(4.921878, 43.580393, 15.468747, 47.517202)

# == BBox used for the slope maps ==
bbwalps = BBox(5.625, 43.581, 7.734, 46.558)
bbwvalps = BBox(5.54, 43.581, 7.734, 46.558).snap_to_xyz(z=12)

# bbsalps = BBox(7.734, 45.583, 11.250, 47.517) # "Small" central europe
bbcalps = BBox(7.734, 45.583, 11.953, 47.517)
bbealps = BBox(11.953, 46.073, 14.062, 47.754)
bbwalps_p = BBox(5.624999, 43.580393, 7.734378, 46.558862)
bbsalps_p = BBox(7.734378, 45.583291, 11.249998, 47.517202)
# bbcalps_p = BBox(7.734378, 45.583291, 11.953127, 47.517202)
bbealps_p = BBox(11.953127, 46.073229, 14.062497, 47.754101)

bbmontblancz10 = BBox(6.855466, 45.828796, 7.207031, 45.951147)

# == BBox used for the topo maps ==
# Kompass south-west: Como-Starlex ✓
bbkcomo = BBox(9.140628, 45.829, 10.371093, 46.679594)
# Kompass Dolomites, split to align with bccalps<>bbealps (11.953) ✓
bbkdolow = BBox(10.371094, 45.829, 11.953124, 47.5172)
# Kompass Dolomites east, up to where the nice map stops
bbkdoloe = BBox(11.953125, 46.437856, 12.480468, 47.754093)
# Kompass Mittersil-Salzbourg-Klagenfurt
bbksalzbourg = BBox(12.480469, 46.558861, 14.238281, 47.754093)

bbkeast = BBox(11.953125, 46.073231, 12.832, 47.754093)

# == Tests ==
foo = BBox(7.7, 46.5, 7.8, 46.6)

class BBoxTest(TestCase):

    def test_snap(self):
        self.assertEqual(foo.snap_to_xyz(1), BBox(0.0, 0.0, 180.0, 85.0511287798066))
        self.assertEqual(foo.snap_to_xyz(2), BBox(0.0, 0.0, 90.0, 66.51326044311186))
        self.assertEqual(foo.snap_to_xyz(9), BBox(7.03125, 46.07323062540836, 8.4375, 47.04018214480666))
        self.assertEqual(foo.snap_to_xyz(16),BBox(7.6959228515625, 46.498392258597626, 7.80029296875, 46.600393037345476))

    def test_intersect(self):
        assert not bbwalps.intersect(bbcalps)
        assert not bbcalps.intersect(bbealps)
        assert not bbealps.intersect(bbwalps)
        assert foo.intersect(bbcalps)
        assert foo.intersect(bbwalps)
        assert bbcalps.intersect(foo)
        assert bbwalps.intersect(foo)
        assert not foo.intersect(bbealps)
        assert not bbealps.intersect(foo)
