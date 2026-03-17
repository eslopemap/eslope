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
            parts = line.strip().split()
            slope = float(parts[0])
            if parts[1].startswith('#'):
                hex_color = parts[1].lstrip('#')
                r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            else:
                elems = [float(p) for p in parts[1:]]
                if len(elems) < 4:  # transparency: opaque by default
                    elems.append(1)
                r, g, b = elems[0], elems[1], elems[2]
            yield slope, r/255, g/255, b/255

# color = Type[Union[float, int]]

def srgb_to_mpl_palette_nearest(palette: Iterable[Tuple[float, float, float, float]]):
    '''Nearest version, like gdal color-relief -nearest_color_entry'''
    eps = 0.1**9  # epsilon
    cdict = {'red': [], 'green': [], 'blue': []}
    slope, pslope, pr, pg, pb = 0, 0, 0, 0, 0
    for i, (slope, r, g, b) in enumerate(palette):
        cutoff_slope = 0 if i == 0 else (slope + pslope) / 2
        for cname, pv, v in (('red', pr, r), ('green', pg, g), ('blue', pb, b)):
            if i == 0:
                pv = v
            cdict[cname].append((cutoff_slope / Ndegrees, pv, v))
        pslope, pr, pg, pb = slope, r, g, b
    if slope != 1:  # if missing, fill in up to 90° / last element
        for cname in cdict:
            _slope, _before, after = cdict[cname][-1]
            cdict[cname].append((1, after, after))
    return cdict


def srgb_to_mpl_palette_interp(palette: Iterable[Tuple[float, float, float, float]]):
    '''Interpolate an srgb palette into a matplotlib gradient,
       to imitate gdal color-relief default'''
    cdict = {'red': [], 'green': [], 'blue': []}
    slope = 0
    for i, (slope, r, g, b) in enumerate(palette):
        for cname, v in (('red', r), ('green', g), ('blue', b)):
            if i == 0 and slope != 0:
                cdict[cname].append((0, v, v))
            cdict[cname].append((slope / Ndegrees, v, v))
    if slope != 1:  # if missing, fill in up to 90° / last element
        for cname in cdict:
            _slope, _before, after = cdict[cname][-1]
            cdict[cname].append((1, _before, after))
    return cdict


# import hsluv
# for i in range(len(cdict['red'])):
#     r, g, b = cdict['red'][i], cdict['green'][i], cdict['blue'][i]
#     print(r, g, b, hsluv.rgb_to_hsluv((r, g, b)))

def plot_mpl_palette(name, cdict, is_nearest):
    if False:
        # from pprint import pprint; pprint(cdict)
        for i, (s, bef, af) in enumerate(cdict['red']):
            print(('{:.1f}' + ' {:.0f}→{:.0f}'*3).format(
                s*90, bef*255, af*255, cdict['green'][i][1]*255, cdict['green'][i][2]*255,
                cdict['blue'][i][1]*255, cdict['blue'][i][2]*255))

    dpi = 10  # values per degree
    dpiseg = 10 if is_nearest else 2
    offset = 0.4 if is_nearest else 0
    xlim = 70
    themap = LinearSegmentedColormap(name, segmentdata=cdict, N=Ndegrees*dpiseg)

    gradient = np.linspace(0, 1,  Ndegrees*dpi+1)
    gradient = np.vstack((gradient, gradient))

    fig, ax = plt.subplots(figsize=(10,2))

    ax.imshow(gradient, aspect='auto', cmap=themap)
    ax.set_title(name, fontsize=14)
    ax.set_yticks([])
    ticklabels = [0,10,20,30,35,40,45,50,55,60,65,70]
    ax.set_xticks([(t + offset) * dpi for t in ticklabels])
    ax.set_xticklabels(ticklabels[:-1] + ['90°'])
    ax.set_xlim([0,(xlim+offset)*dpi])
    return fig


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: {} <-n|-c> <name>".format(sys.argv[0]))
        print("  Plot a slope .clr palette as a colorbar image.")
        print("  -n  nearest-color mode (like gdal -nearest_color_entry)")
        print("  -c  interpolated mode (like gdal color-relief default)")
        print("  <name>  palette name, reads gdaldem-slope-<name>.clr from ../data/")
        print("  Output: colormap-<name>.png in current directory")
        sys.exit(1)
    _, mode, name = sys.argv
    is_nearest = sys.argv[1] == '-n'
    src = 'gdaldem-slope-{}.clr'.format(name)
    dest = 'colormap-' + name
    print (src, '->', dest)
    srgb_to_mpl = srgb_to_mpl_palette_nearest if is_nearest else srgb_to_mpl_palette_interp
    fig = plot_mpl_palette(name.replace('near', ''), srgb_to_mpl(clr_to_srgb(src)), is_nearest)
    fig.savefig(dest)

# from pprint import pprint
# pprint(srgb_to_mpl_palette(clr_to_srgb('/home/me/code/eddy-geek/slope-ign-alti/gdaldem-slope-oslo.clr')))
