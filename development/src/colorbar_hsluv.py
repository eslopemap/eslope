#!/usr/bin/env python3

import sys
from typing import List, Tuple, Union
# import numpy as np
# import matplotlib.pyplot as plt
# from matplotlib.colors import LinearSegmentedColormap
import hsluv
from colorbar import plot_mpl_palette, srgb_to_mpl_palette

# name = sys.argv[1] if len(sys.argv) > 1 else 'oslo'
# name = 'olso'

Ndegrees = 90
# structure expected by matplotlib.
# unlike the input, each color can have different "gradient segments"
cdict = {'red': [], 'green': [], 'blue': []}



def clr_as_hsl(clr_path, outf=sys.stdout):
    """ Print clr file asboth RGB and HSLuv for visual debugging """
    print(clr_path + 'as hsluv:', file=outf)
    with open(clr_path) as f:
        for line in f:
            # nv is "no data" value, usually transparent
            if line.startswith('nv'): continue
            elems = list(map(float, line.strip().split()))
            if len(elems) < 5:  # transparency: opaque by default
                elems.append(255)
            slope, r, g, b, a = elems
            s = "{:<8s} | {: 4d} {: 4d} {: 4d} | {: 6.0f} {: 6.0f} {: 6.0f} ".format(
                line.strip().split()[0], int(r), int(g), int(b),
                *hsluv.rgb_to_hsluv((r/255, g/255, b/255)))
            print(s, file=outf)


def linear(start, stop, vmin=None, vmax=None):
    def gen(i):
        val = (stop-start) * i + start
        if vmin is not None: val = max(vmin, val)
        if vmax is not None: val = min(vmax, val)
        return val
    return gen

import math
"""https://j.holmes.codes/20150808-better-color-gradients-with-hsluv/"""
dtor = lambda d: d * math.pi / 180  # degrees => radians
rtod = lambda r: r * 180 / math.pi  # radians => degrees

def circular(start, stop, forward:bool=True):
    if not forward:
        start, stop = stop, start
    if start > stop:
        stop = stop + 360
    if forward:
        return lambda i: (start + (stop - start) * i + 360) % 360
    return lambda i: (start + (stop - start) * (1-i) + 360) % 360


# for i in range (0,15+1):  print(hsluv.rgb_to_hsluv(make_hsl_gradient((128, 266, True), (100, 100), (90, 32.3))(i/15)))
# print()
# for i in range (0,15+1):  print(hsluv.rgb_to_hsluv(make_hsl_gradient((266, 128, True), (100, 100), (90, 32.3))(i/15)))
# print()
# n=30
# for i in range (0,n+1):  print(hsluv.rgb_to_hsluv(make_hsl_gradient((128, 266, False), (100, 100), (90, 32.3))(i/n)))


def make_hsl_gradient(h_range: Union[Tuple[int, int], Tuple[int, int, bool]],
                      s_range: Tuple[float, float],
                      l_range: Tuple[float, float]): # -> Tuple[float, float, float]:
    h = circular(*h_range)  #type:ignore
    s = linear(*s_range)
    l = linear(*l_range)
    return lambda i: hsluv.hsluv_to_rgb((h(i), s(i), l(i)))


def to256(x):
    return round(x*256)

def gen_hslo_gradient(slopes: List[float], h, s, l, debug=False):
    slope_start, slope_end = slopes[0], slopes[-1]

    for slope in slopes:
        i = (slope - slope_start) / (slope_end - slope_start)
        r, g, b = map(abs, hsluv.hsluv_to_rgb((h(i), s(i), l(i))))  #type:ignore
        if debug:
            print('{: 4.0f} {: 4.0f} {: 4.0f} {: 4.0f}   # {: 4.0f} {: 4.0f} {: 4.0f}'.format(slope, 255*r, 255*g, 255*b, h(i), s(i), l(i)))
        yield slope, r, g, b

def fixd(n):
    return lambda i: n

if __name__ == '__main__':
    import os
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        clr_path = sys.argv[1]
        clr_as_hsl(clr_path)
    else:
        from numpy import arange
        from itertools import chain
        # luminance = lambda i: linear(90, 75)(i/.3) if i < .3 else linear(75, 30, 55)((i-.3)/.7)
        palette = list(chain(
            [(0, 1, 1, 1)], # white
            # slopes, hue green->blue, saturat, luminance light -> dark
            gen_hslo_gradient(arange(10, 28), fixd(127.7),  fixd(100), linear(100,90)),
            gen_hslo_gradient(arange(28, 58, .5), circular(110, 246, False), fixd(100), linear(92, 20, 55)),
            gen_hslo_gradient(arange(58, 61, .5), fixd(246), linear(100, 0), fixd(33)),
            # [(90, .3, .3, .3)]
        ))
        with open('../data/gdaldem-slope-hslo.clr', 'w') as f:
            for slope, r, g, b in palette:
                print('{: 5.1f} {: 4.0f} {: 4.0f} {: 4.0f}'.format(slope, 255*r, 255*g, 255*b), file=f)

        palette1 = list(chain(
            [(0, 1, 1, 1)], # white
            gen_hslo_gradient(arange(10, 28, .5), fixd(127.7),  fixd(100), linear(100,92)),
            gen_hslo_gradient(arange(28, 57, .5), circular(110, 266, False), fixd(100), linear(92, 20, 55)),
            [
                (59, *hsluv.hsluv_to_rgb((266,100,33))),  # blue
                (60, *hsluv.hsluv_to_rgb((0,0,33))) # dark grey
            ]))
        with open('../data/gdaldem-slope-hslo2.clr', 'w') as f:
            for slope, r, g, b in palette1:
                print('{: 5.1f} {: 4.0f} {: 4.0f} {: 4.0f}'.format(slope, 255*r, 255*g, 255*b), file=f)

        palette2 = list(chain(
            [(0, 1, 1, 1)], # white
            gen_hslo_gradient(arange(10, 28, .5), fixd(127.7),  fixd(100), linear(100,92)),
            gen_hslo_gradient(arange(28, 42, .5), circular(110, 12, False), fixd(100), linear(92, 53)),
            gen_hslo_gradient(arange(42, 57, .5), circular(12, 266, False), fixd(100), linear(53, 40)),
            [
                (59, *hsluv.hsluv_to_rgb((266,100,33))),  # blue
                (60, *hsluv.hsluv_to_rgb((0,0,33))) # dark grey
            ]))
        with open('../data/gdaldem-slope-hslo2.clr', 'w') as f:
            for slope, r, g, b in palette2:
                print('{: 5.1f} {: 4.0f} {: 4.0f} {: 4.0f}'.format(slope, 255*r, 255*g, 255*b), file=f)
        # palette1 = list(chain(
        #     [(0, 1, 1, 1)], # white
        #     gen_hslo_gradient((10, 22), always(127.7),  always(100), linear(100,90)),
        #     gen_hslo_gradient(
        #         # slopes, hue green->blue, saturat, luminance light -> dark
        #         (23, 56), circular(127, 266, False), always(100), linear(90, 22, 33)
        #     ), [
        #         (59, *hsluv.hsluv_to_rgb((266,100,33))),  # blue
        #         (60, *hsluv.hsluv_to_rgb((0,0,33))) # dark grey
        #     ]))
        fig = plot_mpl_palette('hslo', srgb_to_mpl_palette(palette))
        fig.savefig('../../img/geo/hslo-colormap-gradient.png')
        fig.show()
        fig = plot_mpl_palette('hslo1', srgb_to_mpl_palette(palette1))
        fig.savefig('../../img/geo/hslo1-colormap-gradient.png')
        fig.show()
        fig = plot_mpl_palette('hslo2', srgb_to_mpl_palette(palette2))
        fig.savefig('../../img/geo/hslo2-colormap-gradient.png')
        fig.show()

# from pprint import pprint
# pprint(srgb_to_mpl_palette(palette))

# TODO:
# take an input clr (eventually, osloed but 'simplified' ie without the manual stops)
# convert each 'stop' to hsl
# interpolate between stops, with intervals of 0.3° (eg 29,30 -> 29,29.3,29.6,29.9,30) -- or 3° if < 30
# convert back to hsl ; write to stdout
# (colormap.py can then take from stdin)
# why? see https://j.holmes.codes/20150808-better-color-gradients-with-hsluv/
# and check https://www.perceptualcolor.org/ -> edges of the G->R->B triangle look perfect for 20->40->50

# themap = LinearSegmentedColormap(name, segmentdata=cdict, N=Ndegrees)

# gradient = np.linspace(0, 1,  Ndegrees)
# gradient = np.vstack((gradient, gradient))

# fig, ax = plt.subplots(figsize=(10,2))

# ax.imshow(gradient, aspect='auto', cmap=themap)
# ax.set_title(name, fontsize=14)
# ax.set_yticks([])
# ax.set_xticks([10,20,30,35,40,45,50,55,60])
# ax.set_xlim([0,60])

# fig.savefig(name + '.png')

