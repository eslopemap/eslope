import sys
assert sys.version_info >= (3,7)
from dataclasses import dataclass, astuple

@dataclass
class BBox:
    """The field order maps gdal's `-te_srs WGS84 -te 7.38 44 7.44 44.15`"""
    w: float
    s: float
    e: float
    n: float
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
    def astuple(self):
        return astuple(self)
    def __str__(self) -> str:
        return f'{self.w} {self.s} {self.e} {self.n}'

bbwalps = BBox(5.625, 43.581, 7.734, 46.558)
bbcalps = BBox(7.734, 45.583, 11.249, 47.517)
bbealps = BBox(11.249, 46.073, 14.062, 47.754)
foo = BBox(7.7, 46.5, 7.8, 46.6)

assert not bbwalps.intersect(bbcalps)
assert not bbcalps.intersect(bbealps)
assert not bbealps.intersect(bbwalps)
assert foo.intersect(bbcalps)
assert foo.intersect(bbwalps)
assert bbcalps.intersect(foo)
assert bbwalps.intersect(foo)
assert not foo.intersect(bbealps)
assert not bbealps.intersect(foo)
