#!/usr/bin/env python3

import sys
from typing import Iterable, Tuple, Type, Union
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap


Ndegrees = 90
# structure expected by matplotlib.
# unlike the input, each color can have different "gradient segments"

# with open(src) as f:
#     slope = 0
#     for line in f:
#         # nv is "no data" value, usually transparent
#         if line.startswith('nv'): continue
#         elems = list(map(float, line.strip().split()))
#         if len(elems) < 5:  # transparency: opaque by default
#             elems.append(255)
#         slope, r, g, b, a = elems
#         for cname, v in (('red', r), ('green', g), ('blue', b)):
#             cdict[cname].append((slope / Ndegrees, v/255, v/255))
#     if slope != 1:  # if missing, fill in up to 90° / last element
#         for cname in cdict:
#             _, before, after = cdict[cname][-1]
#             cdict[cname].append((1, before, after))

def clr_to_srgb(clr_path):
    with open(clr_path) as f:
        slope = 0
        for line in f:
            # nv is "no data" value, usually transparent
            if line.startswith('nv'): continue
            elems = [float(elem)/255 for elem in line.strip().split()]
            if len(elems) < 5:  # transparency: opaque by default
                elems.append(1)
            slope, r, g, b, a = elems
            yield slope, r, g, b

# color = Type[Union[float, int]]

def srgb_to_mpl_palette(palette: Iterable[Tuple[float, float, float, float]]):
    cdict = {'red': [], 'green': [], 'blue': []}
    slope = 0
    for i, (slope, r, g, b) in enumerate(palette):
        for cname, v in (('red', r), ('green', g), ('blue', b)):
            if i == 0 and slope != 0:
                cdict[cname].append((0, v, v))
            cdict[cname].append((slope / Ndegrees, v, v))
    if slope != 1:  # if missing, fill in up to 90° / last element
        for cname in cdict:
            _, before, after = cdict[cname][-1]
            cdict[cname].append((1, before, after))
    return cdict

# from pprint import pprint; pprint(cdict)

# import hsluv
# for i in range(len(cdict['red'])):
#     r, g, b = cdict['red'][i], cdict['green'][i], cdict['blue'][i]
#     print(r, g, b, hsluv.rgb_to_hsluv((r, g, b)))

def plot_mpl_palette(name, cdict):
    themap = LinearSegmentedColormap(name, segmentdata=cdict, N=Ndegrees)

    gradient = np.linspace(0, 1,  Ndegrees+1)
    gradient = np.vstack((gradient, gradient))

    fig, ax = plt.subplots(figsize=(10,2))

    ax.imshow(gradient, aspect='auto', cmap=themap)
    ax.set_title(name, fontsize=14)
    ax.set_yticks([])
    ax.set_xticks([0,10,20,30,35,40,45,50,55,60])
    ax.set_xlim([0,60])
    return fig


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'oslo'
    src = 'gdaldem-slope-{}.clr'.format(name)
    print (src, '->', name + '.png')
    fig = plot_mpl_palette(name, srgb_to_mpl_palette(clr_to_srgb(src)))
    fig.savefig(name + '.png')

# from pprint import pprint
# pprint(srgb_to_mpl_palette(clr_to_srgb('/home/me/code/eddy-geek/slope-ign-alti/gdaldem-slope-oslo.clr')))
